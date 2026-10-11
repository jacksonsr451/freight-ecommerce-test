# Compatibilidade e evidências — prompt 18

> Registro histórico de prompt 18: a tabela abaixo descreve aquela execução. O Compose/CI atual usa
> PostgreSQL 17.11; consulte `docs/testing/README.md` para a correção de provisionamento.

## Raiz efetiva e ferramentas

A raiz é o diretório que contém este README, `docker-compose.yml`, `backend/` e `frontend/`.
`scripts/dev.py` deriva a raiz de `__file__`; não depende do diretório corrente. `scripts/dev.ps1` e
`scripts/dev.sh` delegam para o mesmo CLI. Python/Poetry pertencem a `backend/`; React/TypeScript,
Node/npm pertencem a `frontend/`. Não há `backend/package.json`.

Versões observadas em Windows 10/11: PowerShell 5.1.26100.9444, Python 3.11.15, Poetry 2.4.0,
Node 24.15.0, npm 11.12.1, Docker 29.4.1 e Compose 5.1.3. WSL2 observado: kernel Linux
6.6.87.2-microsoft-standard-WSL2, Python 3.14.4 e Docker/Compose disponíveis. Python suportado é
`>=3.11,<3.15`; Node é 24.x (mínimo 24.15.0), npm 11.

## Evidência realmente executada neste workspace

| Sistema / comando | Resultado |
|---|---|
| Windows: `python scripts/dev.py doctor`, `env-check`, `compose-check` | PASS; mock offline, sem expor valores |
| Windows: `scripts/dev.ps1 doctor` | PASS; wrapper inicia CLI e detecta ferramentas/daemon |
| Windows: `python scripts/dev.py setup` | PASS; Poetry sync e npm ci, sem lockfile alterado |
| Windows: `python scripts/dev.py check` | PASS; suíte Python via pytest (histórico pré-prompt 19) 280/280, Vitest 54/54, Ruff, ESLint, Prettier, typecheck/build e matriz contratual |
| Windows: `python scripts/dev.py layout` | PASS; Playwright Edge 5/5 (viewports 320, 390, 768, 1280 e keyboard/runtime disclosure) |
| Windows: `python scripts/dev.py smoke` | PASS; FastAPI HTTP, Vite e proxy local |
| Windows: `python scripts/dev.py up` | PASS; imagens backend/frontend, PostgreSQL 17 e os 3 healthchecks |
| Windows: `python scripts/dev.py compose-smoke` | PASS; projeto/volume efêmero isolado, health/proxy e cleanup |
| WSL2: `bash scripts/dev.sh doctor` | PASS como diagnóstico; Python 3.14.4 e Docker disponíveis; Poetry e Node Linux ausentes |
| WSL2: `python3 scripts/dev.py compose-smoke` | PASS; build de imagens Linux, PostgreSQL/backend/frontend saudáveis, health/proxy e cleanup |
| WSL2: suíte Poetry/npm/Playwright de host | PENDING; Poetry e Node Linux ausentes; npm detectado aponta ao runtime Windows e não conta como Node Linux |
| GitHub Actions Windows/Linux | PENDING; workflow adicionado, sem execução observada |
| Packsenvios/transportadora/webhook externos | SKIP intencional; sem credenciais/chamadas reais |

Uma falha inicial em Ruff (`E501` na mensagem de skip do teste browser) foi corrigida; a execução
subsequente da suíte completa passou. O modo Playwright real no Windows e o Compose smoke comprovam
apenas o que a linha evidencia; não homologam API externa. A suíte de layout usa loja/UI local e não
depende de backend remoto.

## Segurança do ambiente local

`setup` copia `.env.example` somente se `.env` não existir. A cópia criada para executar este roteiro
usa exclusivamente valores sintéticos locais e não é evidência de segredo real. `env-check` oculta
valores e limita configuração; testes/migrations/seed usam PostgreSQL de loopback ou o host interno
Compose `db`. Bearer permanece backend-only; pagamento/pedido continuam simulados. O projeto Compose
permanente foi inicializado neste teste e mantém o volume PostgreSQL local quando parado por `down`;
smokes efêmeros usam volumes/nome de projeto próprios e os removem ao final.

## Gaps / decisões

- Linux de host com stack Poetry + Node + Playwright precisa do runner CI ou de ferramentas Linux
  instaladas localmente para trocar PENDING por PASS. O build/runtime Compose Linux passou via WSL2.
- Executar o workflow de GitHub Actions e atualizar esta matriz com URL/ID do run antes de afirmar CI
  verde. O job Windows presume serviço PostgreSQL 14 já instalado no runner `windows-2022`.
- Modelo oficial de import ainda não pode ser exportado: falta a instrução literal da linha 1 e a
  grafia completa dos 28 cabeçalhos, conforme TODO-IMPORT-TEMPLATE.
- Receiver de webhook só habilita com timestamp provider confirmado; parser local fixture aceita
  `unix_seconds`, não prova contrato externo.
- Homologação externa requer autorização explícita, grants/contexto existentes e sequência segura em
  `docs/homologacao.md`.
