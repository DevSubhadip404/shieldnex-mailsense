import os

import dns.exception
import dns.resolver

from email_validator import EmailNotValidError, validate_email
from flask import Flask, jsonify, render_template, request

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024

MAX_EMAILS = 50

# Optional: only addresses independently confirmed by the operator.
VERIFIED_EMAILS = frozenset(
    email.strip().casefold()
    for email in os.getenv("VERIFIED_EMAILS", "").split(",")
    if email.strip()
)


def check_domain(domain):
    """Check whether a domain has possible inbound mail routing."""
    resolver = dns.resolver.Resolver()
    resolver.timeout = 2
    resolver.lifetime = 3

    try:
        records = resolver.resolve(domain, "MX")

    except dns.resolver.NXDOMAIN:
        return "bounce", "The domain does not exist."

    except dns.resolver.NoAnswer:
        # RFC 5321 permits A/AAAA fallback when no MX exists.
        for record_type in ("A", "AAAA"):
            try:
                resolver.resolve(domain, record_type)
                return (
                    "routable",
                    "Address-record fallback exists. Mailbox unconfirmed."
                )
            except dns.resolver.NoAnswer:
                continue
            except dns.resolver.NXDOMAIN:
                return "bounce", "The domain does not exist."
            except dns.exception.DNSException:
                return "unknown", "DNS lookup could not be completed."

        return "bounce", "No MX, A, or AAAA mail-routing records found."

    except dns.exception.DNSException:
        return "unknown", "DNS lookup failed or timed out."

    exchanges = [str(record.exchange) for record in records]

    if exchanges == ["."]:
        return "bounce", "Null MX: this domain does not accept email."

    if "." in exchanges:
        return "unknown", "Conflicting MX configuration detected."

    return (
        "routable",
        "Mail-routing records found. Individual mailbox not confirmed."
    )


def analyze_email(address, domain_cache):
    """Classify one address without SMTP probes or outgoing messages."""
    try:
        validated = validate_email(
            address,
            check_deliverability=False
        )
    except EmailNotValidError as error:
        return {
            "email": address,
            "status": "likely_bounce",
            "reason": f"Invalid address: {error}"
        }

    normalized = validated.normalized
    domain = normalized.rsplit("@", 1)[1].encode("idna").decode("ascii")

    if domain not in domain_cache:
        domain_cache[domain] = check_domain(domain)

    routing, reason = domain_cache[domain]

    if routing == "bounce":
        status = "likely_bounce"

    elif routing == "unknown":
        status = "unknown"

    elif normalized.casefold() in VERIFIED_EMAILS:
        status = "likely_delivered"
        reason = (
            "Previously confirmed mailbox with available mail routing."
        )

    else:
        status = "unknown"

    return {
        "email": address,
        "status": status,
        "reason": reason
    }


@app.get("/")
def home():
    return render_template("index.html")


@app.get("/health")
def health():
    return jsonify(status="ok")


@app.post("/api/analyze")
def analyze():
    payload = request.get_json(silent=True)

    if not isinstance(payload, dict):
        return jsonify(error="A valid JSON request is required."), 400

    raw_addresses = payload.get("emails")

    if not isinstance(raw_addresses, list):
        return jsonify(error="Provide an array of email addresses."), 400

    addresses = []
    seen = set()

    for item in raw_addresses:
        if not isinstance(item, str):
            return jsonify(error="Every address must be text."), 400

        email = item.strip()
        key = email.casefold()

        if email and key not in seen:
            seen.add(key)
            addresses.append(email)

    if not addresses:
        return jsonify(error="Enter at least one email address."), 400

    if len(addresses) > MAX_EMAILS:
        return jsonify(error="Maximum 50 unique addresses allowed."), 400

    cache = {}
    results = [analyze_email(email, cache) for email in addresses]

    summary = {
        "total": len(results),
        "likely_delivered": 0,
        "likely_bounce": 0,
        "unknown": 0
    }

    for result in results:
        summary[result["status"]] += 1

    return jsonify(results=results, summary=summary)


@app.errorhandler(413)
def request_too_large(error):
    return jsonify(error="Request exceeds the size limit."), 413


if __name__ == "__main__":
    app.run(debug=True)
