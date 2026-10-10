# Changelog

All notable changes to this project are documented here. This project follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added

- Local React/Vite storefront, FastAPI/PostgreSQL persistence, catalog/cart/checkout/quote snapshots,
  local simulated orders/payments/fulfillment, diagnostics, and contract-gated freight adapters. These
  capabilities are present in source and historical Git commits; no versioned release is implied.
- MIT license, contributor and security policies, support instructions, GitHub issue templates, and
  Dependabot configuration.
- Architecture, development, testing, local demonstration, security, troubleshooting, and ADR guides.
- Dependency-review and Python/npm audit steps in GitHub Actions.
- Third-party notices for the LGPL-licensed PostgreSQL driver, frontend data/license notices, Docker
  base images, and the contract reference whose redistribution terms are unverified.

### Changed

- Python test runner standardized on `jsr-testrunner`; cross-platform tasks and isolated Compose test
  profile use it.
- Clarified project scope as a local demonstration system: order/payment are simulated and external
  Packsenvios flows are not described as homologated.
- Updated backend, test and frontend containers to run application processes as non-root and preserve
  project/third-party notice files in built images.
- Made the current CI, dependency, license, and security reporting limits explicit.

## Release history

No version tags or published releases are recorded in the repository's Git history as of this change.
Earlier development work is present in Git commits but is not assigned release versions or dates here.
