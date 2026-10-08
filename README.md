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
A aplicação ainda não acessa o banco; não há migrations nesta etapa.

## Convenções e configuração

- Backend em `backend/src/freight_ecommerce`, app factory e schemas Pydantic; pytest em `backend/tests`.
- Frontend TS strict, ESLint flat config, Prettier; Vitest/jsdom com testes junto aos componentes.
- Ruff compartilhado em `.ruff.toml`. Scripts de verificação transversal em `tests/`.
- Backend lê `.env` da raiz; variáveis de processo têm precedência. Configuração ativa: `APP_ENVIRONMENT`.
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
