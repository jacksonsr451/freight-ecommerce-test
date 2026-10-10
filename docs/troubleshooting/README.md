# Troubleshooting

## `doctor` informa Poetry ou Node ausente

Confira PATH, reabra PowerShell/Bash e execute `python scripts/dev.py doctor`. Poetry pertence ao
backend; npm/Node pertence ao frontend. `setup` usa `poetry sync` e `npm ci`.

## `TEST_DATABASE_URL` ausente ou indisponível

Os testes persistentes exigem um PostgreSQL loopback separado. Inicie o Compose normal ou um PostgreSQL
local, exporte `TEST_DATABASE_URL` e repita. O teste Docker isolado pode ser executado com
`python scripts/dev.py compose-test`. O host `db` só é aceito pelo fixture quando o runner foi iniciado
dentro desse perfil Compose de teste.

## Porta já ocupada

Para Compose, defina `POSTGRES_PORT`, `BACKEND_PORT` e `FRONTEND_PORT` em `.env`; para host, altere o
comando/porta do backend e `VITE_PROXY_TARGET` conforme `docs/setup-windows.md`/
`docs/setup-linux.md`. Não abra estas portas para uma rede externa como atalho.

## Browser Playwright não encontrado

Windows usa Edge por padrão. Linux usa Chromium; rode
`node frontend/node_modules/playwright/cli.js install chromium --with-deps` e defina
`PLAYWRIGHT_BROWSER_CHANNEL=chromium`. O teste informa SKIP se browser, Node ou dependências faltarem.

## Docker indisponível

`compose-check` valida o YAML sem daemon, mas `up` e `compose-test` precisam de Docker. No Windows,
inicie Docker Desktop com Linux containers; no Linux, confirme Docker Engine ativo e acesso do usuário
ao daemon.

## Teste async, migration ou seed

Use jsr-testrunner via `python scripts/dev.py test`/`backend-test`; a adaptação async e recursos do
runner estão documentados em `docs/development-testing.md`. Migrations/seed são explícitos, não são
executados no startup. Veja `docs/architecture/domain-persistence.md` antes de reverter migrations.

## Integração externa

Não trate falha de DNS, `202`, estado queued ou fixture local como evidência do provedor. Confira
`docs/homologacao.md` e a fonte `docs/reference/gestao-frete-integracao-ecommerce-teste.md`; não invente
campos ou repita despacho incerto.
