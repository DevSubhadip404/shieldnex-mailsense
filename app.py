import os
import time
import threading
from collections import Counter, deque
from concurrent.futures import ThreadPoolExecutor

import dns.exception
import dns.resolver
from email_validator import EmailNotValidError, validate_email
from flask import Flask, jsonify, render_template, request

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 24 * 1024
app.json.sort_keys = False

MAX_EMAILS = 50
MAX_WORKERS = 6
RATE_LIMIT = 12
RATE_WINDOW = 60

VERIFIED_EMAILS = frozenset(
    value.strip().casefold()
    for value in os.getenv("VERIFIED_EMAILS", "").split(",")
    if value.strip()
)

rate_lock = threading.Lock()
rate_history = {}


def make_domain_result(domain, routing, method, reason,
                       domain_state="unknown", mx_hosts=None):
    return {
        "domain": domain,
        "routing": routing,
        "method": method,
        "reason": reason,
        "domain_state": domain_state,
        "mx_hosts": mx_hosts or [],
        "lookup_ms": 0,
    }


def lookup_domain(domain):
    """Inspect inbound mail routing without contacting SMTP servers."""
    start = time.perf_counter()

    def finish(routing, method, reason,
               domain_state="unknown", mx_hosts=None):
        result = make_domain_result(
            domain, routing, method, reason,
            domain_state, mx_hosts
        )
        result["lookup_ms"] = round(
            (time.perf_counter() - start) * 1000
        )
        return result

    try:
        resolver = dns.resolver.Resolver()
        resolver.timeout = 2
        resolver.lifetime = 4
        records = resolver.resolve(domain, "MX")

    except dns.resolver.NXDOMAIN:
        return finish(
            "bounce", "NONE",
            "The domain does not exist.",
            "missing"
        )

    except dns.resolver.NoAnswer:
        # RFC 5321 supports address-record fallback without MX.
        dns_uncertain = False

        for record_type in ("A", "AAAA"):
            try:
                resolver.resolve(domain, record_type)
                return finish(
                    "routable", record_type,
                    f"{record_type} fallback exists; mailbox unconfirmed.",
                    "found"
                )

            except dns.resolver.NXDOMAIN:
                return finish(
                    "bounce", "NONE",
                    "The domain does not exist.",
                    "missing"
                )

            except dns.resolver.NoAnswer:
                continue

            except dns.exception.DNSException:
                dns_uncertain = True

        if dns_uncertain:
            return finish(
                "unknown", "INCONCLUSIVE",
                "DNS fallback checks were inconclusive."
            )

        return finish(
            "bounce", "NONE",
            "No MX, A or AAAA mail-routing records were found.",
            "found"
        )

    except dns.exception.DNSException:
        return finish(
            "unknown", "INCONCLUSIVE",
            "DNS resolution failed or timed out."
        )

    except Exception:
        app.logger.exception("Unexpected DNS resolver failure")
        return finish(
            "unknown", "INCONCLUSIVE",
            "Mail-routing lookup could not be completed."
        )

    mx_hosts = sorted(
        [
            {
                "host": str(record.exchange).rstrip(".") or ".",
                "priority": int(record.preference),
            }
            for record in records
        ],
        key=lambda item: item["priority"]
    )

    if len(mx_hosts) == 1 and mx_hosts[0]["host"] == ".":
        return finish(
            "bounce", "NULL MX",
            "Null MX: the domain explicitly refuses incoming mail.",
            "found", mx_hosts
        )

    if any(item["host"] == "." for item in mx_hosts):
        return finish(
            "unknown", "MX",
            "Conflicting Null MX and regular MX records.",
            "found", mx_hosts
        )

    if not mx_hosts:
        return finish(
            "unknown", "INCONCLUSIVE",
            "The DNS resolver returned no usable MX records.",
            "found"
        )

    return finish(
        "routable", "MX",
        "MX records are present; individual mailbox existence is unconfirmed.",
        "found", mx_hosts
    )


def safe_lookup(domain):
    try:
        return lookup_domain(domain)
    except Exception:
        app.logger.exception("Unhandled domain lookup error")
        return make_domain_result(
            domain, "unknown", "INCONCLUSIVE",
            "The DNS lookup could not be completed."
        )


def signal(label, state, detail):
    return {
        "label": label,
        "state": state,
        "detail": detail
    }


def parse_address(address):
    try:
        verified = validate_email(
            address,
            check_deliverability=False
        )
        return {
            "original": address,
            "normalized": verified.normalized,
            "domain": verified.ascii_domain,
            "error": None
        }

    except EmailNotValidError as error:
        return {
            "original": address,
            "normalized": None,
            "domain": None,
            "error": str(error)
        }


def analyze_address(parsed, domains):
    address = parsed["original"]

    if parsed["error"]:
        return {
            "email": address,
            "domain": None,
            "status": "likely_bounce",
            "reason": "Invalid email syntax: " + parsed["error"],
            "trace": [
                signal("Syntax", "fail", parsed["error"]),
                signal("Domain", "skip", "Not checked."),
                signal("Mail routing", "skip", "Not checked."),
                signal("Mailbox", "skip", "Not checked."),
            ],
        }

    domain = parsed["domain"]
    info = domains[domain]

    domain_state = {
        "found": "pass",
        "missing": "fail",
        "unknown": "unknown"
    }[info["domain_state"]]

    routing_state = {
        "routable": "pass",
        "bounce": "fail",
        "unknown": "unknown"
    }[info["routing"]]

    previously_confirmed = (
        parsed["normalized"].casefold() in VERIFIED_EMAILS
    )

    if info["routing"] == "bounce":
        status = "likely_bounce"
        mailbox = signal(
            "Mailbox", "skip",
            "Mailbox not checked because mail routing failed."
        )
        reason = info["reason"]

    elif info["routing"] == "unknown":
        status = "unknown"
        mailbox = signal(
            "Mailbox", "unknown",
            "Mailbox cannot be confirmed."
        )
        reason = info["reason"]

    elif previously_confirmed:
        status = "likely_delivered"
        mailbox = signal(
            "Mailbox", "pass",
            "Previously and independently confirmed by the operator."
        )
        reason = (
            "Operator-confirmed address with available mail routing. "
            "Future delivery is not guaranteed."
        )

    else:
        status = "unknown"
        mailbox = signal(
            "Mailbox", "unknown",
            "DNS cannot establish whether this mailbox exists."
        )
        reason = info["reason"]

    return {
        "email": address,
        "domain": domain,
        "status": status,
        "reason": reason,
        "trace": [
            signal("Syntax", "pass", "Address syntax is valid."),
            signal(
                "Domain", domain_state,
                "Domain exists." if domain_state == "pass"
                else "Domain does not exist." if domain_state == "fail"
                else "Domain status is inconclusive."
            ),
            signal("Mail routing", routing_state, info["reason"]),
            mailbox,
        ],
    }


@app.before_request
def apply_rate_limit():
    if request.endpoint != "analyze" or app.config.get("TESTING"):
        return None

    now = time.monotonic()
    client_ip = request.remote_addr or "unknown"

    with rate_lock:
        hits = rate_history.setdefault(client_ip, deque())

        while hits and now - hits[0] >= RATE_WINDOW:
            hits.popleft()

        if len(hits) >= RATE_LIMIT:
            return jsonify({
                "error": "Request limit reached. Try again in a minute."
            }), 429

        hits.append(now)

        # Prevent unbounded growth from inactive IP keys.
        if len(rate_history) > 512:
            for key in list(rate_history):
                queue = rate_history[key]
                while queue and now - queue[0] >= RATE_WINDOW:
                    queue.popleft()
                if not queue:
                    del rate_history[key]

    return None


@app.after_request
def security_headers(response):
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Cache-Control"] = "no-store"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self'; "
        "style-src 'self' https://fonts.googleapis.com; "
        "font-src 'self' https://fonts.gstatic.com; "
        "connect-src 'self'; "
        "img-src 'self' data:; "
        "object-src 'none'; "
        "base-uri 'self'; "
        "frame-ancestors 'none'"
    )
    return response


@app.get("/")
def home():
    return render_template("index.html")


@app.get("/health")
def health():
    return jsonify(status="ok", service="ShieldNex MailSense")


@app.post("/api/analyze")
def analyze():
    started = time.perf_counter()
    payload = request.get_json(silent=True)

    if not isinstance(payload, dict):
        return jsonify(error="A valid JSON object is required."), 400

    emails = payload.get("emails")
    if not isinstance(emails, list):
        return jsonify(error="Provide an array of email addresses."), 400

    addresses = []
    seen = set()

    for email in emails:
        if not isinstance(email, str):
            return jsonify(error="Every address must be text."), 400

        email = email.strip()

        if len(email) > 320:
            return jsonify(error="An address exceeds the length limit."), 400

        key = email.casefold()
        if email and key not in seen:
            seen.add(key)
            addresses.append(email)

        if len(addresses) > MAX_EMAILS:
            return jsonify(error="Maximum 50 unique addresses allowed."), 400

    if not addresses:
        return jsonify(error="Enter at least one address."), 400

    parsed = [parse_address(email) for email in addresses]
    unique_domains = sorted({
        item["domain"] for item in parsed if item["domain"]
    })

    domains = {}

    if unique_domains:
        with ThreadPoolExecutor(
            max_workers=min(MAX_WORKERS, len(unique_domains))
        ) as pool:
            domain_results = list(pool.map(safe_lookup, unique_domains))

        domains = {
            item["domain"]: item for item in domain_results
        }

    results = [
        analyze_address(item, domains) for item in parsed
    ]

    counts = Counter(result["status"] for result in results)
    domain_counts = Counter(
        item["domain"] for item in parsed if item["domain"]
    )

    domain_report = []

    for domain in unique_domains:
        item = dict(domains[domain])
        item["address_count"] = domain_counts[domain]
        domain_report.append(item)

    domain_report.sort(
        key=lambda item: (-item["address_count"], item["domain"])
    )

    return jsonify({
        "results": results,
        "domains": domain_report,
        "summary": {
            "total": len(results),
            "likely_delivered": counts["likely_delivered"],
            "likely_bounce": counts["likely_bounce"],
            "unknown": counts["unknown"],
            "domains": len(unique_domains),
            "duration_ms": round(
                (time.perf_counter() - started) * 1000
            ),
        }
    })


@app.errorhandler(413)
def too_large(error):
    return jsonify(error="Request exceeds the size limit."), 413


if __name__ == "__main__":
    app.run(debug=True)
