# freight-ecommerce-test

**Raiz efetiva: `E:\Softwares\joao\tests`**. Backend, frontend, testes, documentação
e infraestrutura ficam diretamente nesta raiz, sem diretório de projeto intermediário.

Bootstrap local com **Poetry + FastAPI + Pydantic** e **React + TypeScript + Vite**.
Inclui pytest, Ruff, ESLint, Prettier e Vitest; dependências exatas nos lockfiles.
A tela inicial consulta apenas `/api/health` da API local. Compra, pagamento e pedido
serão simulados; integração Packsenvios pertence a etapas posteriores.

## Pré-requisitos e instalação

- Python 3.11–3.14, Poetry 2.4+; Node 24.15+ na série 24 e npm 11.
- Windows PowerShell 5.1+. A instalação baixa pacotes; testes locais não exigem serviços remotos.
- Docker Desktop com engine Linux acessível somente para executar Compose.

Na raiz atual:

```powershell
# Apenas na primeira configuração; não sobrescreva um .env existente.
Copy-Item -LiteralPath ".env.example" -Destination ".env"
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\dev.ps1 Install
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\dev.ps1 Check
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\dev.ps1 Smoke
```

Saia de venvs de outros projetos antes de `Install`. Poetry cria `backend/.venv`.
`Install` usa `poetry sync` e `npm ci`. `Check` confere locks, lint, formatação,
testes, typecheck/build e matriz contratual. `Format` aplica formatters.
`Smoke` inicia FastAPI/Vite em portas locais livres, verifica HTTP e proxy e encerra seus processos.
`-ExecutionPolicy Bypass` vale apenas para o processo de PowerShell iniciado.

## Inicialização no host

```powershell
# Terminal 1, nesta raiz
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\dev.ps1 Backend
# Terminal 2, nesta raiz
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\dev.ps1 Frontend
```

- Frontend: <http://127.0.0.1:5173>
- Backend: <http://127.0.0.1:8000/api/health>
- Swagger local: <http://127.0.0.1:8000/docs>
- Encerrar com `Ctrl+C`. Frontend usa proxy Vite; não chama Packsenvios.

## Docker Compose

```powershell
docker compose config --quiet
docker compose up --build -d --wait
docker compose ps
# Para encerrar serviços preservando o volume do banco:
docker compose down
```

Compose é destinado ao desenvolvimento: PostgreSQL 17, FastAPI e Vite com healthchecks.
Portas podem ser configuradas em `.env` (`POSTGRES_PORT`, `BACKEND_PORT`, `FRONTEND_PORT`).
Credenciais do exemplo são somente sintéticas/locais. No host, ajuste também `VITE_PROXY_TARGET`
ao mudar a porta da API. No Compose, proxy usa `http://backend:8000`.
O domínio e a migration inicial estão implementados. A API de bootstrap ainda não usa o banco;
o healthcheck não verifica persistência. Migrations não são executadas automaticamente.

## Persistência e migrations (prompt 03)

SQLAlchemy 2 + psycopg, UUIDs locais, centavos inteiros, `timestamptz` UTC e JSONB para snapshots.
`DATABASE_URL` é exclusiva do backend e aponta ao PostgreSQL **local**; no Compose usa host `db`.
Os 16 modelos e transições estão em `backend/src/freight_ecommerce/domain/`.

```powershell
# Após iniciar PostgreSQL local e configurar DATABASE_URL em .env:
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\dev.ps1 Migrate
# Conferir o estado (a partir desta raiz):
poetry -C backend run alembic current
poetry -C backend run alembic check
```

Para testar persistência, escolha uma configuração de teste local:

```powershell
# Banco local acessível; testes só criam/removem schemas aleatórios freight_test_* próprios.
$env:TEST_DATABASE_URL = 'postgresql+psycopg://freight_local:local_demo_only@127.0.0.1:5432/freight_local'
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\dev.ps1 PersistenceCheck
```

Alternativamente, defina `TEST_POSTGRES_BIN` para a pasta que contém `initdb` e `pg_ctl`:
a fixture inicia/encerra um cluster temporário próprio em loopback. Sem qualquer variável,
testes PostgreSQL são **SKIP explícito**, não PASS; testes de domínio/offline continuam executáveis.
`PersistenceCheck` exige uma dessas variáveis. Para rodar toda a suíte com PostgreSQL,
defina a variável e use `Check`.

Reversão exclusivamente em banco local descartável: `poetry -C backend run alembic downgrade base`;
esse comando remove os dados do domínio. A suíte prova reversibilidade dentro de schemas próprios.
Nenhum seed com dados reais ou credencial Packsenvios é necessário.
Decisões, invariantes, lacunas e evidências: `docs/architecture/domain-persistence.md`.

## Convenções e configuração

- Backend em `backend/src/freight_ecommerce`, app factory e schemas Pydantic; pytest em `backend/tests`.
- Frontend TS strict, ESLint flat config, Prettier; Vitest/jsdom com testes junto aos componentes.
- Ruff compartilhado em `.ruff.toml`. Scripts de verificação transversal em `tests/`.
- Backend lê `.env` da raiz; variáveis de processo têm precedência. Configurações: `APP_ENVIRONMENT`
  e `DATABASE_URL` (armazenada como `SecretStr`, sem exposição pelo healthcheck).
- Vite usa apenas `VITE_*` públicos. Nunca colocar credencial Bearer em variável `VITE_*`.
- `FREIGHT_*` do exemplo são reservas server-only para etapa posterior, sem adapter neste bootstrap.
- `.gitignore` exclui `.env`, venvs, node_modules, builds e logs. `.dockerignore` exclui segredos do build.
- `manual_only: true` jamais habilita contratação automática; seleção de opção será vínculo local.
- Ler `docs/reference/gestao-frete-integracao-ecommerce-teste.md` antes da integração externa.
- Documentos de auditoria copiados são históricos; esta raiz efetiva supersede os caminhos anteriores.

## Estrutura

```text
.
├── backend/          # Poetry, FastAPI, Pydantic, pytest
├── frontend/         # React, TypeScript, Vite, Vitest
├── tests/            # Smoke HTTP e conferência contratual
├── docs/reference/   # Documento original
├── docs/architecture/
├── infra/            # Dockerfiles e notas
├── scripts/dev.ps1
├── .env.example
├── .gitignore
└── docker-compose.yml
```

Evidências de execução e limitações: `docs/architecture/bootstrap-current-root.md`.
