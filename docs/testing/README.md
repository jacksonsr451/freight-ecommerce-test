# Testes

Framework Python: `jsr-testrunner==0.1.0` (import `testrunner`). Os testes frontend usam Vitest; a
jornada visual usa Playwright.

## Executar

Na raiz do repositório, com `TEST_DATABASE_URL` configurada para PostgreSQL de teste loopback:

```text
python scripts/dev.py test
python scripts/dev.py backend-test
python scripts/dev.py persistence-check
python scripts/dev.py layout
python scripts/dev.py smoke
python scripts/dev.py check
```

Sem banco de teste, `check` falha de forma explícita antes de executar a suíte backend completa; não
interprete teste PostgreSQL omitido como PASS. `TEST_POSTGRES_BIN` permite subir um cluster temporário
com `initdb`/`pg_ctl` nos sistemas que o têm instalado. Os fixtures só criam/removem schemas
`freight_test_*` próprios.

Para PostgreSQL efêmero em container:

```text
python scripts/dev.py compose-test
```

## Conteúdo coberto

Os 18 módulos Python cobrem domínio/estados, validação, catálogo, autenticação local, carrinho, quote,
checkout, orders/pagamentos simulados, importação/dispatch/tracking, webhooks, diagnósticos e
persistência. Testes async rodam em asyncio pelo hook/fixtures documentados em
`docs/development-testing.md`. Fixtures HTTP são sintéticas; nenhum teste local faz homologação real
Packsenvios.

O teste browser `test_store_browser` requer Node/dependências frontend e Edge no Windows ou Chromium
Playwright no Linux. Quando esses requisitos não existem, o runner registra SKIP com motivo. O CI
configura browser nos dois sistemas; uma execução com SKIP não prova jornada browser naquele ambiente.

## Validação do provisionamento CI/PostgreSQL 17.11

| Ambiente realmente executado neste workspace | Resultado |
|---|---|
| Windows 10/11, binários oficiais EDB 17.11, `initdb`/`pg_ctl`, porta loopback aleatória | PASS; `pg_isready`, migration e migration-check passaram; `python scripts/dev.py check` executou 280/280 Python e 54/54 Vitest, incluindo browser Edge; cluster temporário parado ao final. |
| Linux container `postgres:17.11-alpine` pelo Compose test profile | PASS; 279 Python passaram e o browser test foi SKIP porque a imagem backend-test não contém Node/Chromium. Projeto, container, rede e volume temporários removidos. |
| Linux Node 24 container (imagem frontend local) | PASS; ESLint, Prettier, 54/54 Vitest, typecheck e build. |
| GitHub-hosted `ubuntu-latest`/`windows-latest` Actions | PENDING; workflow provisiona PostgreSQL 17.11 por container Linux e cluster EDB temporário Windows, mas nenhum run remoto foi observado. |

O workflow Windows não consulta nem presume nome/estado de serviço PostgreSQL instalado: verifica SHA-256
do arquivo binário 17.11, executa `initdb`, escolhe uma porta loopback disponível, aguarda `pg_isready`
e encerra o cluster com `pg_ctl`. No Linux o container declara Docker healthcheck, e o step espera o
estado `healthy`. Ambos executam `migrate`, `migration-check` e a suíte via jsr-testrunner contra banco
descartável. O resultado do runner Linux container não substitui o resultado de Actions no host Linux.
