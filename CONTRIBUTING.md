# Contributing

Thanks for considering a contribution. The project is a local e-commerce/freight demonstration; changes
must preserve the documented contract and keep simulated operations distinct from external provider
operations.

## Set up the environment

Follow the platform guide from the repository root:

- Windows: `docs/setup-windows.md`
- Linux: `docs/setup-linux.md`

The backend environment is Poetry-managed under `backend/`; frontend tools are npm-managed under
`frontend/`. Do not add Python test dependencies to npm or frontend packages to Poetry.

## Branches and commits

Create a focused branch such as `feat/short-description`, `fix/short-description`, `docs/short-description`,
or `chore/short-description`. Match the existing commit style (`feat:`, `fix:`, `docs:`, `refactor:`,
`chore:`) with a concise imperative summary. Keep changes scoped and avoid bundling unrelated formatting
or generated files.

## Before opening a pull request

Run the checks relevant to the change; for a full local gate with loopback PostgreSQL configured:

```text
python scripts/dev.py env-check
python scripts/dev.py check
python scripts/dev.py smoke
python scripts/dev.py layout
```

For Python-only changes, at minimum run `python scripts/dev.py backend-test` and Ruff. For frontend-only
changes, run `python scripts/dev.py frontend-check` and `python scripts/dev.py layout` if UI behavior
changes. Never describe skipped browser/database/CI checks as passed.

Optional local hooks:

```text
pipx install pre-commit
pre-commit install
pre-commit run --all-files
```

Pre-commit is a contributor tool, not an application dependency. Its hooks run Ruff, ESLint and
Prettier; PostgreSQL/browser tests remain explicit commands and CI gates.

PRs should include: purpose, user-visible effects, relevant issues, changed contracts, commands run and
their actual results, migration/rollback impact, and screenshots only when useful. Do not include
`.env`, credentials, bearer values, webhook secrets, real personal data, database dumps, or logs with
sensitive values.

## Integration boundary changes

- Read `docs/reference/gestao-frete-integracao-ecommerce-teste.md` before changing provider behavior.
- Do not invent endpoints, fields, response meanings, grants, company/location discovery, import headers,
  webhook signature formats, retries, shipment acceptance, labels, or delivery semantics.
- Keep bearer credentials server-only. Never place provider credentials in `VITE_*`, browser storage,
  URLs, test artifacts, logs, or public diagnostics.
- Keep mock/synthetic evidence separate from HTTP calls to an authorized external environment.
- External tests require explicit authorization and must document exact environment and evidence.
- Do not change purchase/payment simulation to imply a real payment gateway or carrier contract.

## Review and compatibility

CI targets `ubuntu-latest` and `windows-latest`. Keep paths and subprocess calls portable, preserve
PowerShell/Bash wrappers through `scripts/dev.py`, and avoid OS-specific absolute paths. Tests that need
PostgreSQL must use owned loopback databases/schemas; do not point them at production or shared data.
Reviewers should check behavior, security boundaries, tests, documentation and dependency/license impact.
