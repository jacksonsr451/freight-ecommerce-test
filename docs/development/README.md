# Desenvolvimento local

Consulte o guia do seu sistema: [`setup-windows.md`](../setup-windows.md) ou
[`setup-linux.md`](../setup-linux.md). O ponto de entrada compartilhado é `python scripts/dev.py`;
PowerShell e Bash usam wrappers finos `scripts/dev.ps1` e `scripts/dev.sh`.

## Fluxo diário

```text
python scripts/dev.py doctor
python scripts/dev.py setup
python scripts/dev.py env-check
python scripts/dev.py backend
python scripts/dev.py frontend
```

Execute backend e frontend em terminais separados. Para rodar a suíte Python + frontend:

```text
python scripts/dev.py test
```

Configure `TEST_DATABASE_URL` para um database de teste loopback antes de executar `test`, `check` ou
`persistence-check`. O teste Compose usa seu próprio PostgreSQL temporário:

```text
python scripts/dev.py compose-test
```

## Qualidade local

```text
python scripts/dev.py lint
python scripts/dev.py backend-check
python scripts/dev.py frontend-check
python scripts/dev.py build
python scripts/dev.py smoke
python scripts/dev.py layout
python scripts/dev.py check
```

Os comandos de check executam jsr-testrunner, Ruff, ESLint, Prettier, Vitest, TypeScript e build
conforme a tarefa escolhida. Veja `docs/development-testing.md` para o adapter asyncio do runner.

Opcionalmente, instale `pre-commit` na ferramenta do desenvolvedor e rode `pre-commit install`; os
hooks configurados executam Ruff/ESLint/Prettier. O CI continua sendo o gate completo para testes com
PostgreSQL e browser.

## Variáveis de ambiente

`setup` copia `.env.example` para `.env` apenas se `.env` não existir. `.env` permanece fora do Git e
do contexto Docker. Segredos Packsenvios pertencem ao backend; nunca defina credenciais em `VITE_*`.
Use valores sintéticos localmente e não compartilhe `.env`/logs sem redaction.
