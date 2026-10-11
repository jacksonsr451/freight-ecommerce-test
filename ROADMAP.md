# Roadmap

This roadmap distinguishes code currently present from work that is only proposed. It does not promise
external access, a production deployment, or provider behavior absent from the contract source.

## Implemented

- React/TypeScript/Vite local storefront, FastAPI API, PostgreSQL persistence, Alembic migrations,
  synthetic catalog seed, and local diagnostics.
- Cart, checkout details, freight quote snapshots, local manual-option selection, simulated payment and
  orders, local fulfillment/tracking events, and persisted webhook receipts.
- Server-side Packsenvios quote client plus gated import, dispatch, tracking-refresh, and webhook paths
  whose real use requires authorized configuration; local scenarios remain synthetic.
- Windows/Linux development tasks, jsr-testrunner test suite, frontend tests, and Compose test profile.
- Active `main` Ruleset requires Windows/Linux tests, Code Owner review, squash-only merges, and protects
  deletion/force-push; a pull-request bypass is limited to the repository owner.

## In progress / verification pending

- Execute the GitHub Actions Windows/Linux matrix after these governance and audit changes are pushed.
- Execute a native Linux host setup/test run. Linux Compose tests have run in a Linux container; this is
  not the same evidence as host setup on a Linux workstation.
- Configure a private security reporting route in the GitHub repository settings.

## Contract and operational follow-ups

- Confirm the exact official import-template instruction/header format before enabling compatible
  export; see `docs/homologacao.md` and `TODO-IMPORT-TEMPLATE`.
- Verify permission to redistribute the copied provider contract document before distributing a source
  bundle; its terms are not established by this repository and it is explicitly outside the MIT grant.
- Confirm the provider webhook timestamp format and authorized destination before enabling delivery
  handling; local `unix_seconds` is a test adapter, not proof of the provider contract.
- Perform externally authorized quote/import/dispatch/tracking/webhook validation before claiming
  homologation. HTTP 202, queued work, local status and synthetic tracking do not prove carrier
  acceptance or delivery.
- Define a production hosting/security/migration/operations plan only if production deployment becomes
  an explicit project goal. Current Compose files are for local development and testing.
