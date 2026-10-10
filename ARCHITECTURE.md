# Architecture

`freight-ecommerce-test` is a local e-commerce/freight integration demonstration. Its implemented
purchase and payment path is simulated. Provider-facing code is server-side and based only on
`docs/reference/gestao-frete-integracao-ecommerce-teste.md`; external authorization and homologation
remain separate requirements.

## Components

```text
Browser (React/TypeScript/Vite)
        │ same-origin /api (Vite proxy in development)
        ▼
FastAPI application factory ── SQLAlchemy 2 / psycopg ── PostgreSQL
        │
        └── HTTPX async client → Packsenvios (only when explicitly configured/authorized)
```

- **Frontend:** React, TypeScript, Vite, React Router, TanStack Query, Zod, Vitest and Playwright. The
  browser stores a local cart UUID, not credentials, buyer secrets, or provider identifiers. Requests
  use same-origin `/api`; there is no browser-side Packsenvios client or Bearer header.
- **Backend:** FastAPI app factory at `backend/src/freight_ecommerce/main.py`. Routers cover catalog,
  carts, quote orchestration, simulated orders, guarded local admin, import/dispatch/tracking adapters,
  webhook receipts and diagnostics.
- **Persistence:** PostgreSQL 17, SQLAlchemy ORM with synchronous sessions/transactions, Psycopg and
  Alembic revisions `0001`–`0006`. Tests operate on random owned schemas. Compose's normal DB volume is
  persistent; its test profile uses a temporary project/volume.
- **External HTTP:** HTTPX `AsyncClient` is created on the backend, uses the configured Bearer only on
  server-side calls, disables redirects and `trust_env`, and applies explicit timeouts/retry rules per
  operation. Mock mode uses synthetic transport and does not contact the provider.

## Request and state flows

1. The browser reads products and sends product IDs, quantities, revisions and checkout details to the
   local API. Commercial values, inventory and freight context are derived/validated server-side.
2. Quote requests are persisted with idempotency context and snapshots before the UI receives public
   projections. Choosing `manual_only` is a local snapshot link, not a shipment purchase.
3. Order creation and payment outcomes are local simulations. Only explicit simulated approval reserves
   inventory in a transaction. Fulfillment/tracking events in the local demo are simulation state.
4. Configured import/dispatch/tracking calls use the server adapter and explicit credentials/context.
   Enqueued/pending/uncertain results are not interpreted as carrier acceptance or delivery.
5. A configured webhook receiver verifies an HMAC, validates company/location context and persists an
   idempotent receipt before acknowledging. Receipts remain `reconciliation_pending`; the application
   does not ship a background worker. An optional in-process notifier hook can be injected by a host,
   but no production queue/worker is included.

## Security and trust boundaries

- Public catalog/runtime APIs have no customer account or session-authentication system. Carts use
  anonymous UUIDs; that is not account authentication.
- Local admin routes use `X-Local-Admin-Key` only outside production. Production settings disable
  these endpoints. This is a demonstration control, not a complete production identity/authorization
  system.
- Provider Bearer, webhook HMAC secret and database URL are backend settings (`SecretStr` where
  applicable); the frontend only receives public mode/status projections. `.env` is local and ignored.
- No permissive CORS middleware is configured; development uses the Vite proxy. Compose host-published
  ports bind to `127.0.0.1`; container services listen on their container network for peer access.
- Health is process liveness only. `/api/diagnostics` returns local/redacted operational information;
  it does not prove provider connectivity.
- Webhook timestamp unit and official import-template formatting remain contract gaps; local parsers and
  fixtures are not evidence of provider behavior.

## Runtime and deployment scope

`docker-compose.yml` is a development stack: PostgreSQL, FastAPI and Vite with healthchecks. Migrations
and seed are explicit. `infra/backend.Dockerfile` installs only Poetry `main` dependencies. The
`backend-test` profile uses `infra/backend-test.Dockerfile` with dev dependencies and testrunner.
Application and test containers run as non-root users. There is no production image/deployment
pipeline, reverse-proxy configuration, customer authentication, real payment system or external job
worker in this repository. See `docs/deployment/demo.md` before running the local demonstration.

## Related decisions

- External contract and route matrix: `docs/architecture/contract-matrix.md` and
  `docs/reference/gestao-frete-integracao-ecommerce-teste.md`.
- Persistence and migrations: `docs/architecture/domain-persistence.md`.
- Async test bridge: `docs/development-testing.md`.
- Security reporting status: `SECURITY.md`.
- Historical ADR notes: `docs/architecture/decisions.md`; current scoped decision:
  `docs/adr/0001-local-demo-and-provider-boundaries.md`.
