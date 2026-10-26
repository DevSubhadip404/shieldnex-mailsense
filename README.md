# ShieldNex MailSense

**Email Deliverability Intelligence**

An independent software development internship selection project
prepared for ShieldNex Aerospace.

MailSense is a Flask web application for batch email validation
and mail-routing analysis.

## Features

- Professional responsive dashboard
- Bulk validation of up to 50 email addresses
- Email syntax validation
- MX record and domain checks
- A/AAAA mail-routing fallback
- Null MX detection
- Three result classifications with explanations
- Summary statistics
- CSV report export
- DNS caching within each analysis request
- Automated tests
- No outgoing email messages

## Technology

- Python and Flask
- dnspython
- email-validator
- HTML5, CSS3 and JavaScript
- Gunicorn
- Pytest

## How It Works

1. Users paste a list of email addresses.
2. Duplicate addresses are removed.
3. The backend validates email syntax.
4. DNS records are checked to establish mail routing.
5. The application classifies each address.
6. Results are shown in the dashboard and can be exported.

## Classification Rules

### Likely Delivered

The address must have been independently confirmed by the
application operator and have available mail routing.

This status does not guarantee future delivery.

### Likely Bounce

Returned for invalid syntax, nonexistent domains,
Null MX records, or domains without usable mail routing.

### Unknown

Returned when the domain has possible mail routing but
the individual mailbox cannot be confirmed, or when
DNS lookups are inconclusive.

Most valid addresses will return Unknown because MX
records cannot establish individual mailbox existence.

## Run Locally

Requires Python 3.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
python app.py
```

Open http://127.0.0.1:5000

## Optional Confirmed Addresses

If you own and have independently confirmed an address:

```bash
export VERIFIED_EMAILS="your-confirmed-address@gmail.com"
python app.py
```

Use only addresses that are actually confirmed.

Without this configuration, the Likely Delivered category
will normally remain empty. This is intentional.

## Automated Tests

```bash
python -m pytest -v
```

Tests use mocked DNS results where appropriate to avoid
depending on external network conditions.

## Deploy on Render

Create a new Render Web Service connected to this repository,
or use the included render.yaml Blueprint.

- Runtime: Python
- Build: pip install -r requirements.txt
- Start: gunicorn app:app --timeout 180
- Health endpoint: /health

## Hosting Limitations

Render Free services block outbound connections on SMTP ports
25, 465 and 587.

MailSense does not use SMTP and does not send messages.

The deployed application CAN:

- Validate email syntax
- Check DNS and MX records
- Detect a Null MX configuration
- Check A/AAAA fallback records
- Report independently confirmed addresses if configured

The deployed application CANNOT:

- Guarantee an email will be delivered
- Confirm arbitrary mailbox existence
- Reliably detect catch-all mail servers
- Verify inbox placement
- Guarantee delivery past spam filtering

If DNS is unavailable, a domain's result is Unknown.

## Privacy and Security

- Submitted addresses are processed in memory.
- No database is used.
- No message content is sent or stored.
- No SMTP mailbox probing is performed.
- DNS resolvers may observe queried domain names.
- Each request has address and payload size limits.
- CSV export escapes spreadsheet formula-like values.

This is a limited demonstration tool, not a production-scale
mail validation service.

## Project Disclaimer

Independent candidate work for an internship selection task.
Not an official or endorsed ShieldNex Aerospace product.
