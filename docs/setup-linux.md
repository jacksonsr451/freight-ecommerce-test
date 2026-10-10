# Setup — Linux

## Requisitos

- Linux x86_64, Bash, Git, Python 3.11–3.14.
- Poetry 2.4+, Node 24.x (mínimo 24.15.0) e npm 11.x.
- Docker Engine + Docker Compose v2 para o fluxo em containers.

Em Debian/Ubuntu, instale os pacotes de sistema equivalentes a `python3`, `python3-venv`, `pipx`,
`git`, `curl` e `ca-certificates`; use `pipx install poetry==2.4.0`. Para Node, use um gerenciador de
versões ou distribuição oficial que instale Node 24 e npm 11. A aplicação não depende de bashisms no
Python/React; `scripts/dev.sh` é apenas um wrapper Bash fino.

## Setup e verificações

Na raiz do repositório:

```bash
python3 scripts/dev.py doctor
python3 scripts/dev.py setup
python3 scripts/dev.py env-check
```

`setup` não substitui `.env` existente; executa `poetry sync` em `backend/` e `npm ci` em `frontend/`.
Alternativamente, use `bash scripts/dev.sh setup`. O wrapper delega à mesma implementação Python.
Não use npm no diretório backend.

## PostgreSQL, migrations e testes

Use PostgreSQL de desenvolvimento/teste em loopback. O Compose local também inicia PostgreSQL 17:

```bash
python3 scripts/dev.py up
python3 scripts/dev.py migrate
python3 scripts/dev.py seed
export TEST_DATABASE_URL='postgresql+psycopg://freight_local:local_demo_only@127.0.0.1:5432/freight_local'
python3 scripts/dev.py check
python3 scripts/dev.py persistence-check
```

Os testes criam e removem somente schemas aleatórios próprios. Não configure `TEST_DATABASE_URL` para
produção, host remoto ou banco compartilhado. Alternativamente, `TEST_POSTGRES_BIN` aponta para um
PostgreSQL local que possua `initdb` e `pg_ctl`; a fixture inicia e encerra um cluster descartável.
`check` falha explicitamente se não houver uma dessas opções, em vez de omitir os testes PostgreSQL.

## Execução no host

Use dois terminais na raiz:

```bash
python3 scripts/dev.py backend
python3 scripts/dev.py frontend
```

Ou use `bash scripts/dev.sh backend` e `bash scripts/dev.sh frontend`. O servidor frontend encaminha
`/api` ao backend local; Bearer Packsenvios permanece server-only.

## Docker Compose

```bash
python3 scripts/dev.py compose-check
python3 scripts/dev.py up
docker compose ps
python3 scripts/dev.py down
```

`down` mantém o volume persistente. `python3 scripts/dev.py compose-smoke` cria um projeto/volume
temporário exclusivo, verifica backend, banco e proxy e remove somente esses recursos próprios.
Compose aguarda healthchecks, mas migrations e seed continuam explícitos.

## Playwright e solução de problemas

```bash
node frontend/node_modules/playwright/cli.js install chromium --with-deps
export PLAYWRIGHT_BROWSER_CHANNEL=chromium
python3 scripts/dev.py layout
python3 scripts/dev.py smoke
```

- `python3 scripts/dev.py doctor` verifica ferramentas sem expor valores de configuração.
- Se o Docker daemon estiver indisponível, `compose-check` ainda valida YAML, mas `up`/`compose-smoke`
  falham; registre runtime Docker como FAIL/SKIP conforme a execução, não como PASS.
- Portas padrão podem ser alteradas em `.env` (`POSTGRES_PORT`, `BACKEND_PORT`, `FRONTEND_PORT`).
- Modo real não confirma autorização, oferta, homologação ou disponibilidade externa.
