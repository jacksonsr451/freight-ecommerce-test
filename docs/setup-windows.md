# Setup — Windows 10/11

## Requisitos

- Windows 10/11, PowerShell 5.1+ e Git.
- Python 3.11–3.14 e Poetry 2.4+.
- Node 24.x (mínimo 24.15.0) e npm 11.x.
- Docker Desktop com Linux containers somente para o fluxo Compose.

Instale Poetry como ferramenta de usuário (por exemplo, via pipx) e confirme `python`, `poetry`,
`node` e `npm` no `PATH`. Os manifests ficam separados: `backend/pyproject.toml` + `poetry.lock` são
Python; `frontend/package.json` + `package-lock.json` são React/Node. Não execute npm no backend.

## Setup e verificações

Na raiz do repositório, em PowerShell:

```powershell
python scripts/dev.py doctor
python scripts/dev.py setup
python scripts/dev.py env-check
```

`setup` copia `.env.example` para `.env` somente se `.env` ainda não existir, faz `poetry sync` em
`backend/` e `npm ci` em `frontend/`. Edite somente `.env` local; nunca use valores reais em `VITE_*`.
Wrapper equivalente: `scripts/dev.ps1 setup` (delega à mesma implementação Python).

Para executar no host, use terminais separados na raiz:

```powershell
python scripts/dev.py backend
python scripts/dev.py frontend
```

## PostgreSQL, migrations e testes

Inicie PostgreSQL local ou Compose. Para Compose: `python scripts/dev.py up`; para migrar e popular
somente o banco local configurado: `python scripts/dev.py migrate` e `python scripts/dev.py seed`.
Migrations/seeds recusam `APP_ENVIRONMENT=production` e database host que não seja loopback ou o host
interno Compose `db`.

Os testes de persistência exigem um banco de teste loopback. Os testes criam e removem apenas schemas
aleatórios próprios; prefira um database separado. Em PowerShell:

```powershell
$env:TEST_DATABASE_URL = 'postgresql+psycopg://freight_local:local_demo_only@127.0.0.1:5432/freight_local'
python scripts/dev.py check
python scripts/dev.py persistence-check
python scripts/dev.py layout
python scripts/dev.py smoke
```

Alternativamente, defina `TEST_POSTGRES_BIN` para um diretório PostgreSQL que contenha `initdb.exe` e
`pg_ctl.exe`; a fixture sobe um cluster descartável em loopback. Sem essas variáveis, `check` para com
erro explícito em vez de declarar a suíte PostgreSQL como PASS.

Playwright usa Edge headless por padrão no Windows. Para Chromium instalado com Playwright, defina
`PLAYWRIGHT_BROWSER_CHANNEL=chromium` e execute
`node frontend/node_modules/playwright/cli.js install chromium`.

## Docker Compose

```powershell
python scripts/dev.py compose-check
python scripts/dev.py up
docker compose ps
python scripts/dev.py down
```

`down` preserva o volume PostgreSQL. `python scripts/dev.py compose-smoke` usa um nome de projeto e
portas temporários próprios, verifica saúde/proxy/diagnóstico e remove somente seu volume temporário.
Nunca use `docker compose down --volumes` no projeto normal se precisar preservar dados locais.

## Problemas comuns

- `poetry`/`npm` ausente: revise `PATH`, reabra PowerShell e rode `python scripts/dev.py doctor`.
- PostgreSQL: confirme que `DATABASE_URL`/`TEST_DATABASE_URL` usam host loopback; `db` só resolve
  dentro da rede Compose.
- Porta ocupada: configure `POSTGRES_PORT`, `BACKEND_PORT` e `FRONTEND_PORT` em `.env` antes do `up`.
- Docker engine parado: `docker compose config --quiet` verifica YAML, mas Compose runtime exige
  Docker Desktop ativo com Linux containers.
- Cotação real: configure somente no backend. Compra, pagamento e pedido continuam simulados.
