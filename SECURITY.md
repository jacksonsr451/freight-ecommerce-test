# Security policy

## Scope

This is a local demonstration application. The security scope includes this repository, its CI and
Compose files, FastAPI/React code, synthetic test fixtures, and the server-side external API adapters.
It does not include the security of Packsenvios, a carrier, GitHub, Docker images' upstream software,
or an external deployment operated by someone else.

There is no production deployment configuration, customer account/authentication system, payment
gateway, or provider homologation in this project. Local admin keys are for development/test only and
are rejected in `APP_ENVIRONMENT=production`. The app's simulated order/payment state is not a financial
control. The quote bearer and inbound webhook secret belong only in the backend secret store.

## Reporting vulnerabilities

The GitHub repository is public. A private vulnerability-reporting channel has not been configured or
verified from this workspace. **Do not put credentials, exploit details, personal data, or other
sensitive information in a public issue.** The maintainer must enable and verify GitHub's private
vulnerability reporting (Repository → Security → Report a vulnerability) before private disclosure can
be accepted. Until that route is available, the private reporting contact is a documented governance
gap; no email address or alternate private channel is being invented here.

For non-sensitive defects, use the public bug-report issue form. Do not include unredacted traces,
request bodies, bearer headers, HMAC secrets, database URLs/passwords, customer/order data, or `.env`.

## Credentials and sensitive data

- Keep `.env` local and out of Git; `.env.example` contains only local synthetic values and empty
  provider-secret fields.
- Store `FREIGHT_API_KEY` and `PACKSENVIOS_WEBHOOK_SECRET` only in an authorized backend environment;
  never reuse the webhook secret as the bearer credential.
- Never expose secret values in `VITE_*`, browser storage, URLs, diagnostics, screenshots, test output,
  or logs. Rotate any credential that is accidentally disclosed.
- Fixtures and evidence must use synthetic values. Redact email, tax IDs, addresses, tokens and response
  bodies before sharing logs.
- PostgreSQL tests create random `freight_test_*` schemas and must use an owned loopback/test database.

## Existing controls and limitations

- Backend, frontend and test processes run as non-root users in their Docker images; the PostgreSQL
  image retains its upstream container defaults.
- Host-published Compose ports bind to loopback. The backend listens on all interfaces inside its
  container so the Compose frontend can reach it; do not publish it directly to an untrusted network.
- The frontend uses same-origin `/api` via Vite and does not send Packsenvios bearer credentials.
- FastAPI does not install permissive CORS middleware; browser development is through the local proxy.
- The liveness endpoint checks process liveness, not database or provider availability.
- `npm audit --audit-level=high` returned zero known vulnerabilities during this audit. `pip-audit`
  2.10.1 reported no known vulnerabilities among installed third-party Python packages; it skipped the
  local project package because that package is not published on PyPI. The workflow is configured to
  audit the installed Poetry environment. These scans do not prove absence of unknown vulnerabilities.
