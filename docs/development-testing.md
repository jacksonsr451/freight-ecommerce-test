# Desenvolvimento e testes Python — jsr-testrunner

## Framework verificado

O projeto instala `jsr-testrunner==0.1.0` no grupo de desenvolvimento do Poetry. O console é
`testrunner` e o import público é `testrunner`; o pacote não depende do módulo `pytest`.

O URL passado originalmente (`github.com/jacksonsr451/jsr-testrunner`) retorna 404. Os metadados do
wheel 0.1.0 apontam para o repositório público `github.com/jacksonsr451/test-runner`, um fork cuja
documentação e fonte renomeiam a API pública para `testrunner` e hooks para `testrunner_*`. Foram
consultados o `METADATA`, `testrunner.__init__`, o código instalado de fixtures/hooks e as páginas de
fixtures, parametrização, assertions, monkeypatch, plugin API e referência API. A versão do ambiente do
projeto foi verificada com `poetry run testrunner --version`.

- [Fonte e README](https://github.com/jacksonsr451/test-runner)
- [Fixtures](https://github.com/jacksonsr451/test-runner/blob/main/doc/en/how-to/fixtures.rst)
- [Parametrização](https://github.com/jacksonsr451/test-runner/blob/main/doc/en/how-to/parametrize.rst)
- [Mocks/monkeypatch](https://github.com/jacksonsr451/test-runner/blob/main/doc/en/how-to/monkeypatch.rst)
- [Plugins/hooks](https://github.com/jacksonsr451/test-runner/blob/main/doc/en/how-to/writing_plugins.rst)
- [Referência de API](https://github.com/jacksonsr451/test-runner/blob/main/doc/en/reference/reference.rst)

## Baseline e cobertura migrada

- Antes da migração: 18 módulos `test_*.py`, **280 casos coletados** incluindo todos os conjuntos
  parametrizados. Na execução de referência imediatamente antes da migração: 279 passaram e a jornada
  browser falhou intermitentemente; execução isolada dessa jornada passou. Uma execução anterior no
  Windows também registrou 280/280 PASS.
- Após portar namespaces/configuração: **280 casos coletados** (110 funções de teste assíncronas e 33
  síncronas antes da expansão de parâmetros). Uma execução completa inicial com o runner novo produziu
  279 PASS e a mesma jornada browser falhou em outra asserção visual; os demais unitários, assíncronos
  e PostgreSQL passaram. É uma instabilidade pré-existente do E2E/browser, não supressão/remoção do
  caso. A jornada browser passou em execução isolada com o runner novo.
- Foram mantidos todos os 18 arquivos de teste e suas asserções, cenários negativos, parâmetros,
  exceções, integração FastAPI/PostgreSQL e verificações de concorrência. A coleta antes/depois manteve
  o total exato 280. O teste browser não foi removido nem convertido em skip por padrão; ele só pula
  quando Node/dependências/browser não estão disponíveis, como antes.
- Os mocks usam `unittest.mock.AsyncMock`, HTTPX `MockTransport` e a fixture `monkeypatch` do runner.
  Fixtures de sessão/função, autouse, yield/teardown, `tmp_path`, `tmp_path_factory`, `capsys` e `caplog`
  continuam fornecidos pelo runner.

## Async: incompatibilidade observada e adaptação

O próprio testrunner declara que não executa coroutine test/fixture sem plugin. O plugin de AnyIO
instalado registra no grupo pytest de entry points e importa `pytest`/`_pytest`, portanto não é
compatível com esta suíte sem reintroduzir o framework removido. A configuração desativa autoload de
plugins externos (`--disable-plugin-autoload`) e `backend/tests/_testrunner_support.py` implementa
somente o hook `testrunner_pyfunc_call` documentado no `conftest.py`:

- Cada teste recebe event loop asyncio de escopo função.
- Testes `async def` rodam nesse loop por `run_until_complete`.
- As fixtures async generator/coroutine registradas com `async_fixture` executam setup, corpo e
  teardown no mesmo loop e preservam o `yield`/cleanup.
- A suite anterior usava apenas o backend asyncio (incluía fixtures `anyio_backend` que fixavam esse
  backend); Trio nunca foi uma cobertura do projeto.

Isto não implementa o runner nem replica o sistema geral de fixtures. Se a suíte passar a exigir Trio,
fixtures async de escopo maior ou execução concorrente de testes, a adaptação precisa ser revista com
novos testes de comportamento.

## Recursos auditados

- Fixtures: function e session scope, autouse, dependências, yield teardown, `request`, temp paths.
- Parametrização: `testrunner.mark.parametrize` mantida para os mesmos dados/casos.
- Exceções/skip/fail: `testrunner.raises` (incluindo `match` e `excinfo`), `testrunner.skip`,
  `testrunner.fail`; asserções continuam `assert` nativo.
- Testes: sync e async, FastAPI `AsyncClient`/`ASGITransport`, PostgreSQL por schemas aleatórios,
  constraints/migrations/concurrency e jornada browser real.
- Plugins anteriores: somente o plugin AnyIO de pytest (`pytest11`); `pytest-asyncio`, `pytest-cov` e
  `pytest-mock` não eram dependências instaladas. A aplicação continua usando AnyIO como dependência
  runtime transitiva do FastAPI/Starlette/HTTPX, não o plugin pytest.

## Executar

Na raiz do repositório:

```text
python scripts/dev.py doctor
python scripts/dev.py setup
python scripts/dev.py test
python scripts/dev.py check
python scripts/dev.py persistence-check
python scripts/dev.py compose-test
```

`test` executa jsr-testrunner e Vitest; `backend-test` executa somente Python. `check` roda o runner,
Ruff, ESLint, Prettier, Vitest, typecheck, build e matriz contratual. `compose-test` constrói a imagem
de teste com Poetry `dev`, sobe PostgreSQL 17 numa stack Compose isolada e executa testrunner; o
cleanup remove volume/rede/container temporários mesmo em caso de falha. A imagem de backend runtime
usa apenas dependências `main`.

## Dependências e resíduos

- Adicionado: `jsr-testrunner==0.1.0` no grupo Poetry `dev`.
- Removido: dependência direta `pytest`; removida configuração `[tool.pytest.ini_options]`.
- AnyIO, Pluggy e similares permanecem somente se requeridos por produção/testrunner ou metadados de
  terceiros. Menções a `pytest` em extras opcionais de dependências alheias no `poetry.lock` são
  metadados transitivos, não instalação/dependência direta do projeto.
- Registros antigos nos documentos `docs/architecture/` são evidências da execução histórica antes do
  prompt 19; não são comandos atuais. O README e os roteiros Windows/Linux descrevem somente o runner
  atual.

## Resultados da migração

| Plataforma/ambiente | Resultado |
|---|---|
| Windows 10/11 | `python scripts/dev.py test`: 280/280 PASS (inclui browser Edge) + 54/54 Vitest. `check` também passou com Ruff/ESLint/Prettier, typecheck/build e matriz contratual. |
| Linux host | Não executado neste workspace; falta Poetry e Node Linux no WSL2. |
| Compose Linux | `python scripts/dev.py compose-test`: 279 PASS, 1 SKIP browser (Node/Playwright ausentes dentro da imagem de teste), status 0 e cleanup do projeto/volume confirmados. |
| GitHub Actions matriz Linux/Windows | Workflow atualizado para matrix; resultado pendente de execução do CI. |
