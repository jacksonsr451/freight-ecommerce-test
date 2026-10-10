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
