# Bootstrap executado diretamente na raiz atual

> **Registro histórico pré-prompt 19:** comandos/resultados abaixo referem-se ao framework então usado.
> Os comandos atuais de testes usam jsr-testrunner; veja `docs/development-testing.md`.

Data: 08/10/2026. `Get-Location` confirmou **`E:\Softwares\joao\tests`**.
O diretório estava vazio antes da execução. Backend, frontend, testes, documentação
e infraestrutura foram criados diretamente nele; nenhuma pasta intermediária de projeto foi criada.
Este registro supersede os caminhos históricos da auditoria 00 copiada para `docs/architecture`.

## Alterações reais

- Fontes/configurações do bootstrap já validado reutilizadas nesta raiz, sem copiar venv,
  node_modules, dist ou `.git` de outro diretório. Lockfiles foram preservados.
- Nova venv criada em `E:\Softwares\joao\tests\backend\.venv`, pacote backend instalado nela.
- Dependências frontend instaladas em `E:\Softwares\joao\tests\frontend\node_modules` via `npm ci`.
- `.env.example`, `.gitignore`, `.dockerignore`, `docker-compose.yml`, Dockerfiles e README presentes.
- Compose define PostgreSQL 17 com volume persistente, backend FastAPI e frontend Vite,
  com healthchecks e portas loopback. Persistência/Alembic não são implementados pelo bootstrap.
- Git inicializado somente nesta raiz, branch `main`; nenhum commit, staging ou push executado.

## Comandos e resultados

| Comando / operação | Resultado |
|---|---|
| `Get-Location` | `E:\Softwares\joao\tests` |
| `python --version`, `poetry --version`, `node --version`, `npm --version` | Python 3.11.15; Poetry 2.4.0; Node 24.15.0; npm 11.12.1 |
| Cópia explícita de fontes e lockfiles; criação dos arquivos de infraestrutura | Arquivos verificados no disco por leitura/listagem dos diretórios |
| `Get-FileHash -Algorithm SHA256` original e cópia da referência | Idênticos: `D9C92F4FF0708EFC125333D28E86BE1CF944C002B69E909A8D679F1802949595` |
| `powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\dev.ps1 Install` | PASS; 26 dependências backend e pacote local instalados; 234 pacotes npm; npm reportou zero vulnerabilidades naquele momento |
| `powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\dev.ps1 Check` | PASS; lock Poetry, Ruff lint/format, pytest, ESLint, Prettier, Vitest, typecheck/build, matriz contratual |
| pytest | 2 testes passaram, sem warnings |
| Vitest | 4 testes passaram |
| Vite build | Gerou `frontend/dist/index.html` e assets |
| Conferência contratual | 14 rotas/métodos/abilities/linhas coincidem; 3 exemplos JSON válidos; sem HTTP Packsenvios |
| `powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\dev.ps1 Smoke` | PASS; processos reais locais FastAPI/Vite, health HTTP direto + HTML + proxy `/api/health`; processos encerrados ao final |
| `docker compose config --quiet` | PASS; configuração Compose válida, sem exigir daemon |
| `docker compose up --build -d --wait` | FAIL; daemon Docker inacessível, erro exato abaixo |
| `git init -b main`, `git check-ignore --no-index`, `git status --short --untracked-files=all` | Git criado nesta raiz; `.env`, `.env.local`, venv, dependências, dist e `.pem` ignorados; `.env.example` versionável |

## Erros exatos / execução não comprovada

`docker info --format '{{.ServerVersion}}'`:

```text
failed to connect to the docker API at npipe:////./pipe/dockerDesktopLinuxEngine; check if the path is correct and if the daemon is running: open //./pipe/dockerDesktopLinuxEngine: O sistema não pode encontrar o arquivo especificado.
```

`docker compose up --build -d --wait`:

```text
unable to get image 'freight-ecommerce-test-frontend': failed to connect to the docker API at npipe:////./pipe/dockerDesktopLinuxEngine; check if the path is correct and if the daemon is running: open //./pipe/dockerDesktopLinuxEngine: O sistema não pode encontrar o arquivo especificado.
```

**Containers e build Docker não foram validados em execução.** É necessário tornar o daemon
Docker Desktop acessível e repetir `docker compose up --build -d --wait`.
O bootstrap no host foi instalado e validado; essa validação não implica sucesso do Compose.

## Limites

Nenhuma chamada Packsenvios, pagamento real, migration externa ou ação destrutiva foi executada.
O healthcheck confirma a aplicação local, não banco ou serviços externos. Smoke frontend usa HTTP
e Vitest/jsdom, sem navegador real. Configuração server-only de frete está reservada no exemplo,
sem adapter; Bearer não é enviado ao frontend.
