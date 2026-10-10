# Third-party notices

This project is MIT-licensed; that license does not relicense third-party packages, container base
images, the Packsenvios API, marks/services, or the copied contract-reference document. Dependency
lockfiles and upstream package license files remain authoritative. Preserve upstream license and
NOTICE files when redistributing package distributions or images.

## Python dependencies

Direct runtime and development dependencies were inspected from installed package metadata and the
Poetry manifest. Notable licenses:

| Component | License | Notice/obligation |
|---|---|---|
| FastAPI, Pydantic, pydantic-settings, SQLAlchemy, Alembic | MIT | Retain upstream notices with redistributed package copies. |
| Uvicorn, HTTPX | BSD-3-Clause | Retain copyright, conditions and disclaimer from upstream license files. |
| psycopg and psycopg-binary | LGPL-3.0-only | Their installed distributions include LGPL license text. Redistributing an image containing these components remains subject to LGPL-3.0 terms; preserve the license and follow applicable source/relinking obligations. |
| email-validator | Unlicense | See the package's upstream license. |
| python-multipart | Apache-2.0 | Retain the license and any upstream NOTICE file when redistributing. |
| jsr-testrunner | MIT | Retain the upstream license when redistributing the package. |
| Ruff | MIT | Retain the upstream license when redistributing the package. |

The current installed Poetry environment contained license metadata for every distribution inspected,
including the project package after its MIT metadata was added. Other transitive Python packages are
installed from the exact `backend/poetry.lock`; retain each distribution's license files. The lock
also contains optional dependency-extra metadata from third-party packages; a textual reference to a
test extra does not mean that dependency is installed directly by this project.

## Frontend dependencies and data

The exact frontend dependency graph is in `frontend/package-lock.json`; npm package distributions carry
their own license files. A local metadata audit found predominantly MIT packages plus Apache-2.0,
BSD-2-Clause/3-Clause, ISC, BlueOak-1.0.0, MPL-2.0, MIT-0, CC0-1.0 and the following attribution-bearing
data dependency:

- `caniuse-lite` includes browser compatibility data licensed CC-BY-4.0. Attribution: “Data from
  [Can I Use](https://caniuse.com/), via the `caniuse-lite` package”; see the package's `LICENSE` and
  <https://github.com/browserslist/caniuse-lite>.
- `lightningcss` is MPL-2.0; see its `LICENSE` in the package distribution.
- React, React DOM, React Router, TanStack Query, Zod, Vite, Vitest, ESLint and Prettier are MIT in the
  installed package metadata.
- TypeScript and Playwright are Apache-2.0; retain each upstream license/NOTICE when redistributing.

The npm lock records SPDX license metadata for all 269 package entries, including optional platform
variants not installed on this Windows host. Counts in the current lock: 206 MIT, 21 Apache-2.0,
11 ISC, 8 BSD-2-Clause, 3 BSD-3-Clause, 4 BlueOak-1.0.0, 2 MIT-0, 12 MPL-2.0, 1 CC-BY-4.0 and 1
CC0-1.0. The target platform installer selects the relevant optional binaries; their license terms
remain attached to those package distributions. Re-audit after dependency updates.

## CI actions

The GitHub workflow uses `actions/checkout`, `actions/setup-python`, `actions/setup-node`,
`actions/dependency-review-action`, and `pypa/gh-action-pip-audit`. Their upstream repositories publish
their own licenses (MIT for the `actions/*` and dependency-review actions; Apache-2.0 for
`gh-action-pip-audit`). CI actions are not bundled into the application image.

## Docker images

The Dockerfiles use `python:3.11-slim`, `node:24-alpine`, and Compose uses `postgres:17-alpine`. These
images contain operating-system packages in addition to Python/Node/PostgreSQL; retain the upstream
image package/license notices when redistributing a built image. Tags are not digest-pinned, and no
container SBOM/license scan was available during this audit. The project does not republish those base
images as its own source.

## Contract, marks and services

`docs/reference/gestao-frete-integracao-ecommerce-teste.md` is a copied provider contract reference.
Its redistribution permission has not been established by this repository audit. Verify permission
with the document/provider owner before redistributing the reference file or repository bundle.
Packsenvios, carriers, their APIs and marks remain third-party property and are not granted by this
project's MIT license. The software makes no claim to provider endorsement or homologation.
