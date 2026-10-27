# ShieldNex MailSense

### Email Deliverability Intelligence

An independent software development internship selection
project prepared for ShieldNex Aerospace.

MailSense is an explainable email-routing analysis tool built
with Python, Flask, JavaScript, and DNS inspection.

It identifies obvious delivery risks while clearly reporting
cases where individual mailbox existence cannot be confirmed.

## Key Features

### Signal Trace
Four diagnostic stages for every address:
1. Syntax validation
2. Domain assessment
3. Mail-routing assessment
4. Mailbox confirmation status

### Domain Intelligence
- MX record inspection
- MX hostnames and priorities
- Null MX detection
- A/AAAA fallback
- Domain grouping
- Per-domain DNS lookup duration
- In-request DNS caching

### Result Explorer
- Bulk analysis of up to 50 unique addresses
- Status filters
- Searchable results
- Expandable evidence details
- Classification distribution

### Reporting
- CSV export with spreadsheet formula protection
- Print-ready reports that can be saved as PDF
- Summary counts and diagnostic evidence

### Engineering
- Bounded parallel DNS lookups
- Input validation and payload limits
- Simple per-instance request throttling
- Security response headers
- Responsive UI
- Keyboard shortcut: Cmd/Ctrl + Enter
- Automated backend tests

## Classification Methodology

**Likely Delivered**

Only used for an address previously and independently
confirmed by the operator, when DNS mail routing is present.

This is not proof of future delivery.

**Likely Bounce**

Used when syntax is invalid, the domain does not exist,
an exclusive Null MX is configured, or DNS shows no usable
mail-routing records.

**Unknown**

Used when mail routing is available but mailbox existence
cannot be determined, or DNS queries are inconclusive.

Most syntactically valid addresses with MX records will
be classified Unknown unless separately confirmed.

There is intentionally no invented deliverability
percentage or confidence score.

## How the Backend Works

1. Receives a JSON array of email addresses.
2. Removes duplicate addresses.
3. Validates each address using email-validator.
4. Extracts unique domains from valid addresses.
5. Resolves domains with bounded parallel workers.
6. Checks MX records and permitted A/AAAA fallback.
7. Builds a structured diagnostic trace.
8. Returns JSON for the frontend to visualize.

DNS results are reused within a batch.

## Run Locally

Requires Python 3.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
python app.py
```

Visit:

http://127.0.0.1:5000

## Run Tests

```bash
python -m pytest -v
```

The automated tests use mocked DNS responses for
reproducible results without external DNS dependencies.

## Operator-Confirmed Mailboxes

Optionally provide addresses that you own and have
independently confirmed:

```bash
export VERIFIED_EMAILS="your-confirmed-address@gmail.com"
python app.py
```

On Render, configure this as an environment variable
only if you have actual confirmed addresses.

If not configured, Likely Delivered may remain at zero.
That is intentional.

## Deploy on Render

Create a Python Web Service connected to this repository.

Build command:

```bash
pip install -r requirements.txt
```

Start command:

```bash
gunicorn app:app --workers 1 --threads 2 --timeout 180
```

Health check:

`/health`

Alternatively, deploy using render.yaml.

## Hosting and Verification Limitations

Render Free web services block outbound SMTP
connections on ports 25, 465 and 587.

MailSense never makes SMTP connections and never
sends messages.

The deployed application CAN:
- Validate email syntax
- Check MX records
- Check domain DNS status
- Identify Null MX configurations
- Use A/AAAA mail-routing fallback
- Display operator-confirmed addresses if configured

The deployed application CANNOT:
- Guarantee future delivery
- Verify arbitrary mailbox existence
- Reliably detect all catch-all domains
- Verify inbox placement
- Determine whether spam filters would reject a message

Unknown is the correct output when evidence is insufficient.

DNS resolvers or hosting networks can block or time out
DNS requests. These are reported as inconclusive.

## Security and Privacy

- Maximum 50 unique addresses per request
- 24 KB JSON request size limit
- Basic in-memory per-IP request throttling
- Security headers, including a Content Security Policy
- User content rendered safely using textContent
- No database and no persistent email-address storage
- No outgoing email messages
- No SMTP mailbox probing
- DNS queries reveal domain names to resolvers
- Temporary client IP rate-limit counters are held in memory
- Google Fonts hosts may receive standard font-loading requests

The request limiter is per application process and relies
on the observed remote address. It is not a distributed,
production-grade rate limiter and may group users behind
a common reverse proxy.

This is a demonstration application, not a commercial
mail-verification service.

## API

POST `/api/analyze`

Example request:

```json
{
  "emails": [
    "hello@gmail.com",
    "invalid-email"
  ]
}
```

Returns a JSON object with:
- results: email classifications and diagnostic traces
- domains: grouped DNS records and routing findings
- summary: counts, domain count and analysis duration

GET `/health` returns service health information.

## Technology

- Python
- Flask
- dnspython
- email-validator
- HTML5
- CSS3
- JavaScript
- Gunicorn
- Pytest

## Attribution

Independent internship selection task submission
prepared for ShieldNex Aerospace.

Not an official or endorsed company product.
