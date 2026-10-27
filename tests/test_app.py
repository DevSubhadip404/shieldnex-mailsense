import sys
from pathlib import Path

import dns.resolver
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app as project


@pytest.fixture
def client():
    project.app.config["TESTING"] = True
    yield project.app.test_client()
    project.app.config["TESTING"] = False


def fake_lookup(domain, routing="routable"):
    return project.make_domain_result(
        domain=domain,
        routing=routing,
        method="MX",
        reason="Mocked mail-routing result.",
        domain_state="found" if routing != "unknown" else "unknown",
        mx_hosts=[
            {"host": "mail.example.net", "priority": 10}
        ] if routing == "routable" else []
    )


def test_homepage(client):
    response = client.get("/")
    assert response.status_code == 200
    assert b"MailSense" in response.data


def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json["status"] == "ok"


def test_invalid_address(client):
    response = client.post(
        "/api/analyze",
        json={"emails": ["invalid-email"]}
    )

    assert response.status_code == 200
    item = response.json["results"][0]
    assert item["status"] == "likely_bounce"
    assert item["trace"][0]["state"] == "fail"


def test_routable_domain_stays_unknown(client, monkeypatch):
    monkeypatch.setattr(project, "lookup_domain", fake_lookup)

    response = client.post(
        "/api/analyze",
        json={"emails": ["hello@gmail.com"]}
    )

    item = response.json["results"][0]
    assert item["status"] == "unknown"
    assert len(item["trace"]) == 4
    assert item["trace"][2]["state"] == "pass"
    assert item["trace"][3]["state"] == "unknown"


def test_confirmed_address(client, monkeypatch):
    monkeypatch.setattr(project, "lookup_domain", fake_lookup)
    monkeypatch.setattr(
        project,
        "VERIFIED_EMAILS",
        frozenset({"verified@gmail.com"})
    )

    response = client.post(
        "/api/analyze",
        json={"emails": ["verified@gmail.com"]}
    )

    assert response.json["results"][0]["status"] == "likely_delivered"
    assert response.json["results"][0]["trace"][3]["state"] == "pass"


def test_domain_bounce(client, monkeypatch):
    monkeypatch.setattr(
        project,
        "lookup_domain",
        lambda domain: fake_lookup(domain, "bounce")
    )

    response = client.post(
        "/api/analyze",
        json={"emails": ["person@gmail.com"]}
    )

    assert response.json["results"][0]["status"] == "likely_bounce"


def test_dns_unknown(client, monkeypatch):
    monkeypatch.setattr(
        project,
        "lookup_domain",
        lambda domain: fake_lookup(domain, "unknown")
    )

    response = client.post(
        "/api/analyze",
        json={"emails": ["person@gmail.com"]}
    )

    assert response.json["results"][0]["status"] == "unknown"


def test_duplicate_address_removal(client):
    response = client.post(
        "/api/analyze",
        json={"emails": ["bad-email", "BAD-EMAIL", "bad-email"]}
    )

    assert response.json["summary"]["total"] == 1


def test_domain_lookups_are_cached(client, monkeypatch):
    calls = []

    def counted_lookup(domain):
        calls.append(domain)
        return fake_lookup(domain)

    monkeypatch.setattr(project, "lookup_domain", counted_lookup)

    response = client.post(
        "/api/analyze",
        json={"emails": [
            "alice@gmail.com",
            "bob@gmail.com",
            "carol@gmail.com"
        ]}
    )

    assert response.status_code == 200
    assert len(calls) == 1
    assert response.json["summary"]["domains"] == 1
    assert response.json["domains"][0]["address_count"] == 3


def test_more_than_fifty_addresses(client):
    addresses = [f"person{i}@gmail.com" for i in range(51)]

    response = client.post(
        "/api/analyze",
        json={"emails": addresses}
    )

    assert response.status_code == 400


def test_bad_json_shape(client):
    response = client.post(
        "/api/analyze",
        json={"emails": "hello@gmail.com"}
    )
    assert response.status_code == 400


def test_non_string_address(client):
    response = client.post(
        "/api/analyze",
        json={"emails": ["hello@gmail.com", 123]}
    )
    assert response.status_code == 400


def test_security_headers(client):
    response = client.get("/")

    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert "Content-Security-Policy" in response.headers


def test_null_mx(monkeypatch):
    class MXRecord:
        preference = 0
        exchange = "."

    class FakeResolver:
        def resolve(self, domain, record_type):
            return [MXRecord()]

    monkeypatch.setattr(dns.resolver, "Resolver", FakeResolver)

    result = project.lookup_domain("example.com")

    assert result["routing"] == "bounce"
    assert result["method"] == "NULL MX"


def test_address_record_fallback(monkeypatch):
    class FakeResolver:
        def resolve(self, domain, record_type):
            if record_type == "MX":
                raise dns.resolver.NoAnswer()
            if record_type == "A":
                return ["192.0.2.1"]
            raise dns.resolver.NoAnswer()

    monkeypatch.setattr(dns.resolver, "Resolver", FakeResolver)

    result = project.lookup_domain("example.com")

    assert result["routing"] == "routable"
    assert result["method"] == "A"


def test_missing_mail_routing(monkeypatch):
    class FakeResolver:
        def resolve(self, domain, record_type):
            raise dns.resolver.NoAnswer()

    monkeypatch.setattr(dns.resolver, "Resolver", FakeResolver)

    result = project.lookup_domain("example.com")

    assert result["routing"] == "bounce"
    assert result["method"] == "NONE"


def test_request_size_limit(client):
    response = client.post(
        "/api/analyze",
        data="x" * 30000,
        content_type="application/json"
    )

    assert response.status_code == 413
