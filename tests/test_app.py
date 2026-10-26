import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import app as project


@pytest.fixture
def client():
    project.app.config["TESTING"] = True
    return project.app.test_client()


def test_homepage(client):
    response = client.get("/")
    assert response.status_code == 200
    assert b"MailSense" in response.data


def test_health_endpoint(client):
    response = client.get("/health")
    assert response.json["status"] == "ok"


def test_invalid_address(client):
    response = client.post(
        "/api/analyze",
        json={"emails": ["not-an-email"]}
    )

    assert response.status_code == 200
    assert response.json["results"][0]["status"] == "likely_bounce"


def test_routable_domain_is_unknown(client, monkeypatch):
    monkeypatch.setattr(
        project,
        "check_domain",
        lambda domain: ("routable", "MX records found.")
    )

    response = client.post(
        "/api/analyze",
        json={"emails": ["hello@example.com"]}
    )

    assert response.json["results"][0]["status"] == "unknown"


def test_confirmed_address(client, monkeypatch):
    monkeypatch.setattr(
        project,
        "check_domain",
        lambda domain: ("routable", "MX records found.")
    )

    monkeypatch.setattr(
        project,
        "VERIFIED_EMAILS",
        frozenset({"verified@example.com"})
    )

    response = client.post(
        "/api/analyze",
        json={"emails": ["verified@example.com"]}
    )

    assert response.json["results"][0]["status"] == "likely_delivered"


def test_unroutable_domain(client, monkeypatch):
    monkeypatch.setattr(
        project,
        "check_domain",
        lambda domain: ("bounce", "Domain does not exist.")
    )

    response = client.post(
        "/api/analyze",
        json={"emails": ["person@example.com"]}
    )

    assert response.json["results"][0]["status"] == "likely_bounce"


def test_duplicate_removal(client):
    response = client.post(
        "/api/analyze",
        json={"emails": ["bad-email", "BAD-EMAIL", "bad-email"]}
    )

    assert response.json["summary"]["total"] == 1


def test_address_limit(client):
    addresses = [
        f"user{i}@example.com"
        for i in range(51)
    ]

    response = client.post(
        "/api/analyze",
        json={"emails": addresses}
    )

    assert response.status_code == 400


def test_null_mx(monkeypatch):
    class FakeRecord:
        exchange = "."

    class FakeResolver:
        timeout = 2
        lifetime = 3

        def resolve(self, domain, record_type):
            return [FakeRecord()]

    monkeypatch.setattr(
        project.dns.resolver,
        "Resolver",
        FakeResolver
    )

    result, reason = project.check_domain("example.com")

    assert result == "bounce"
    assert "Null MX" in reason
