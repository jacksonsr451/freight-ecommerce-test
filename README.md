# freight-ecommerce-test

Aplicação demonstrativa local de catálogo, carrinho e cotação de frete usando React/TypeScript,
FastAPI e PostgreSQL. **Pedidos e pagamentos são simulados**; comportamento de provedor só é afirmado
quando sustentado pela fonte contratual e evidência de homologação.

**Raiz do repositório:** o diretório que contém este README, `docker-compose.yml`, `backend/` e
`frontend/`. Backend, frontend, testes, documentação e infraestrutura ficam nesta raiz, sem diretório
de projeto intermediário. Os comandos do projeto localizam a raiz a partir do script, não do cwd.

Bootstrap local com **Poetry + FastAPI + Pydantic** e **React + TypeScript + Vite**.
Inclui jsr-testrunner, Ruff, ESLint, Prettier e Vitest; dependências exatas nos lockfiles.
Inclui catálogo, checkout, pedidos/pagamentos simulados, painel administrativo, importação condicionada
e diagnóstico seguro. A cotação pode usar o adapter real; o modo mock e as operações reais de despacho,
tracking e webhook permanecem separados e explicitamente não homologados sem evidência externa.

## Compatibilidade operacional

O ponto de entrada multiplataforma é `python scripts/dev.py <task>`. `scripts/dev.ps1` (PowerShell) e
`scripts/dev.sh` (Bash) são wrappers finos para a mesma implementação. Veja os roteiros completos:

- `docs/setup-windows.md`
- `docs/setup-linux.md`
- `docs/homologacao.md`
- `docs/checklist-go-no-go.md`
- `docs/architecture/compatibility-evidence-prompt18.md`
- `docs/development-testing.md`
- `docs/development/README.md`
- `docs/testing/README.md`
- `docs/deployment/demo.md`
- `docs/security/README.md`
- `docs/troubleshooting/README.md`
- `ARCHITECTURE.md`
- `ROADMAP.md`
- `CHANGELOG.md`
- `CONTRIBUTING.md`
- `CONTRIBUTORS.md`
- `CODE_OF_CONDUCT.md`
- `SECURITY.md`
- `SUPPORT.md`
- `LICENSE`
- `THIRD_PARTY_NOTICES.md`

## Pré-requisitos e instalação (Windows e Linux)

- Python 3.11–3.14, Poetry 2.4+; Node 24.15+ na série 24 e npm 11.
- Windows 10/11 com PowerShell 5.1+; Linux com Bash. Docker Compose v2 para execução em containers.
- Mock é o modo de cotação padrão; testes locais não chamam Packsenvios.

Na raiz do repositório, em PowerShell ou Bash:

```text
python scripts/dev.py setup
python scripts/dev.py env-check
python scripts/dev.py check
python scripts/dev.py smoke
```

`setup` cria `.env` somente se ele não existir, executa `poetry sync` em `backend/` e `npm ci` em
`frontend/`. Poetry instala o backend; npm instala o frontend. `check` exige PostgreSQL de teste,
executa as verificações completas e não trata testes persistentes SKIP como PASS. Detalhes específicos
por sistema: `docs/setup-windows.md` e `docs/setup-linux.md`.

## Testes Python (jsr-testrunner)

O único framework de testes Python próprio é `jsr-testrunner==0.1.0` (import `testrunner`, comando
`testrunner`). O comando padrão, da raiz, é:

```text
python scripts/dev.py test
```

Ele executa a suíte Python com jsr-testrunner e os testes Vitest do frontend. `check` acrescenta lint,
format, build e conferência contratual. `persistence-check` executa somente testes com PostgreSQL.
Defina `TEST_DATABASE_URL` para PostgreSQL loopback de teste; os testes criam e removem somente schemas
`freight_test_*` aleatórios. O adapter local `backend/tests/_testrunner_support.py` agenda corrotinas e
fixtures assíncronas no mesmo event loop asyncio por teste.
Detalhes da migração, baseline e limitações estão em `docs/development-testing.md`.

## Inicialização no host

```text
# Terminal 1
python scripts/dev.py backend
# Terminal 2
python scripts/dev.py frontend
```

- Frontend: <http://127.0.0.1:5173>
- Backend: <http://127.0.0.1:8000/api/health>
- Swagger local: <http://127.0.0.1:8000/docs>
- Encerrar com `Ctrl+C`. Frontend usa proxy Vite; não chama Packsenvios.

## Docker Compose

```text
python scripts/dev.py compose-check
python scripts/dev.py up
docker compose ps
python scripts/dev.py down
```

Compose é destinado ao desenvolvimento: PostgreSQL 17.11, FastAPI e Vite com healthchecks.
Portas podem ser configuradas em `.env` (`POSTGRES_PORT`, `BACKEND_PORT`, `FRONTEND_PORT`).
Credenciais do exemplo são somente sintéticas/locais. No host, ajuste também `VITE_PROXY_TARGET`
ao mudar a porta da API. No Compose, proxy usa `http://backend:8000`.
O domínio e a migration inicial estão implementados. A API de bootstrap ainda não usa o banco;
o healthcheck não verifica persistência. Migrations não são executadas automaticamente.

Para executar toda a suíte Python dentro de um projeto Compose isolado (com perfil de teste, imagem
com dependências dev e PostgreSQL próprios), use `python scripts/dev.py compose-test`. O comando
remove containers, rede e volume temporário no fim; a imagem runtime `backend` continua sem dependências
de teste.

## Persistência e migrations (prompt 03)

SQLAlchemy 2 + psycopg, UUIDs locais, centavos inteiros, `timestamptz` UTC e JSONB para snapshots.
`DATABASE_URL` é exclusiva do backend e aponta ao PostgreSQL **local**; no Compose usa host `db`.
Os 16 modelos e transições estão em `backend/src/freight_ecommerce/domain/`.

```text
# Após iniciar PostgreSQL local e configurar DATABASE_URL em .env:
python scripts/dev.py migrate
python scripts/dev.py migration-current
python scripts/dev.py migration-check
```

Para testar persistência, escolha uma configuração de teste local:

```text
# Defina TEST_DATABASE_URL no ambiente do seu shell; os testes só criam/removem
# schemas aleatórios freight_test_* próprios. Veja setup-windows.md/setup-linux.md.
python scripts/dev.py persistence-check
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

## Catálogo e estoque (prompt 04)

Depois de migrar o PostgreSQL **local**, carregue os produtos sintéticos:

```text
python scripts/dev.py seed
```

O seed cria sete produtos com preços/pesos/dimensões variados, incluindo esgotado e inativo.
É idempotente: não sobrescreve preço, estoque, reservas ou status já alterados por um operador.
Seed é explícito, nunca executado no startup; recusa produção e URL externa de banco.

| Método / caminho local | Uso |
|---|---|
| `GET /api/products?page=1&page_size=20` | Lista pública, somente ativos, até 100 itens/página |
| `GET /api/products/{id}` | Produto ativo com preço, medidas e estoque disponível |
| `POST /api/products/{id}/stock-check` | Corpo `{"quantity": 2}`; valida estoque e calcula subtotal/peso no servidor |
| `GET /api/admin/products` e `GET /api/admin/products/{id}` | Consulta administrativa, inclui inativos/reservas |
| `POST /api/admin/products` | Cria produto e inventário atomicamente |
| `PATCH /api/admin/products/{id}` | Atualização parcial, sem campos nulos ou controle de reservas pelo cliente |
| `DELETE /api/admin/products/{id}` | Exclusão lógica; preserva IDs e referências históricas |

Para o CRUD administrativo em desenvolvimento/testes, defina `LOCAL_ADMIN_KEY` (ao menos 32
caracteres) em `.env` e envie o header `X-Local-Admin-Key`. Vazio desabilita a administração;
em produção ela é bloqueada. Essa chave **não** é a credencial Packsenvios, não é enviada ao
frontend nem definida em `VITE_*`. Exemplo de corpo de criação (dados somente sintéticos):

```json
{
  "sku": "DEMO-EXAMPLE",
  "name": "Produto sintético",
  "price_cents": 2590,
  "weight_grams": 1000,
  "length_cm": 20,
  "width_cm": 15,
  "height_cm": 10,
  "stock_on_hand": 5,
  "status": "active"
}
```

`stock-check` não aceita preço/medidas do cliente e **não reserva estoque**. Disponibilidade é
`on_hand - reserved`; revalidação/reserva na confirmação do pedido pertencem aos prompts 05/11.
Produtos inativos retornam 404 na API pública; ativos esgotados aparecem com disponibilidade zero.
OpenAPI interno: `/docs` e `/openapi.json`. Detalhes/evidências: `docs/architecture/catalog-api.md`.

## Carrinho e cálculo comercial (prompt 05)

Execute `Migrate` para aplicar a revision **0002** antes de usar o carrinho.
O catálogo deve estar populado (por exemplo, com `Seed`). Endpoints são da loja local:

| Método / caminho | Entrada / comportamento |
|---|---|
| `POST /api/carts` | Corpo `{}`; cria carrinho anônimo, revisão 1 |
| `GET /api/carts/{cart_id}` | Consulta itens, preços/pesos atuais, endereço e totais; sincroniza invalidação se o catálogo mudou |
| `POST /api/carts/{cart_id}/items` | `product_id`, `quantity`, `expected_revision`; adiciona unidades e junta à linha existente |
| `PATCH /api/carts/{cart_id}/items/{item_id}` | `quantity`, `expected_revision`; define quantidade absoluta |
| `DELETE /api/carts/{cart_id}/items/{item_id}?expected_revision=N` | Remove a linha e retorna o carrinho recalculado |
| `PUT /api/carts/{cart_id}/address` | `expected_revision`, `address` completo ou `null` para limpar |

Cada resposta contém revisão, itens, subtotal em centavos, peso total em gramas, quantidade,
problemas de disponibilidade, `editable`, `checkout_ready` e `has_current_quote` (metadado local,
não confirmação de contratação). Preço, peso, medidas e totais **não são aceitos do navegador**.

Todas as alterações exigem revisão atual; conflito retorna **409** e exige refetch. Quantidade
positiva até 1000 por produto; limite local de 100 produtos distintos. Para remover use DELETE.
Endereço usa `postal_code` (string de 8 dígitos), `street`, `number`, `district`, `city`, `state`,
`country: BR` e `complement` opcional. Não recebe seletores de empresa/unidade externa.

O carrinho **não reserva estoque**. Dois carrinhos podem conter o mesmo saldo disponível;
confirmação de pedido no prompt 11 deverá revalidar sob locks e reservar atomicamente uma única vez.
Itens que ficaram inativos/esgotados permanecem visíveis com problema, sem permitir checkout.
Mudanças de quantidade, itens/endereço e critérios do catálogo invalidam cotações/tentativas abertas,
preservando seus snapshots e IDs. Carrinho encerrado ou já vinculado a pedido não pode ser alterado.
Detalhes de concorrência, invalidação, migration e evidências: `docs/architecture/cart-commercial.md`.

## Cliente Packsenvios isolado (prompt 06)

O módulo **server-only** `backend/src/freight_ecommerce/freight/` implementa chamadas **de saída**
POST `/api/v1/freight/quotes` e GET `/api/v1/freight/quotes/{quote_request}` conforme a referência.
Esses caminhos não foram registrados como rotas públicas da loja. O motor que ligará carrinho,
persistência e cliente pertence ao prompt 07. Não há compra/seleção/contratação externa neste cliente.

- `FREIGHT_MODE=mock` (default): usa transport HTTP sintético sem rede e sem chave real.
  `FREIGHT_MOCK_SCENARIO=quoted|unavailable|fiscal_review` seleciona a fixture, não regras comerciais/fiscais.
- `FREIGHT_MODE=real`: requer `FREIGHT_BASE_URL` (URL da aplicação, sem sufixo API),
  `FREIGHT_API_KEY` e `FREIGHT_COMPANY_ID` autorizados. Configure unidade quando aplicável.
  HTTPS é exigido fora de loopback; HTTP só é aceito em localhost/127.0.0.1/::1.
- `FREIGHT_ORIGIN_POSTAL_CODE` é opcional; sem origem explícita, uma unidade configurada deve
  permitir a resolução pelo provedor. Empresa sem unidade exige origem no request/configuração.
- Timeouts: `FREIGHT_TIMEOUT_SECONDS=10`, connect `FREIGHT_CONNECT_TIMEOUT_SECONDS=3`.
  `FREIGHT_MAX_ATTEMPTS=2` limita retries; `FREIGHT_MAX_RETRY_WAIT_SECONDS=5` limita espera automática.
  Retry-After maior que o orçamento é devolvido no erro **sem retry antecipado**.
- Chaves/contexto ficam exclusivamente no backend; nunca criar variáveis `VITE_FREIGHT_*` com segredos.

Exemplo backend, sem acoplamento à loja:

```python
from uuid import uuid4
from freight_ecommerce.freight.client import build_freight_client
from freight_ecommerce.freight.schemas import QuoteRequest

async def quote_backend_example():
    async with build_freight_client() as client:
        prepared = client.prepare_quote(QuoteRequest(
            request_key=uuid4(),  # persistir antes do HTTP no motor 07; não regenerar no retry
            origin_postal_code="01001000", destination_postal_code="20040002",
            weight_kg="1.000", declared_value_cents=10000,
            length_cm=20, width_cm=15, height_cm=10, volume_count=1,
        ))
        result = await client.create_quote(prepared)
        same_quote = await client.get_quote(result.data.id)  # não usar request_key nesta rota
        return same_quote
```

Credenciais reais somente de ambiente especificamente autorizado. Código de exemplo por padrão é mock;
não demonstra acesso, oferta ou homologação. O cliente não publica o resultado bruto no navegador.
Fixtures, lacunas, logs e evidências: `docs/architecture/freight-client.md`.

## Motor de cotação e snapshots (prompt 07)

Aplicar `Migrate` para a revision **0003**. Carrinho com produtos ativos/estoque e destino válido
pode ser cotado pelas rotas **locais** abaixo, usando o adapter configurado no backend:

| Método / caminho | Corpo / comportamento |
|---|---|
| `POST /api/carts/{cart_id}/freight-quotes` | `expected_revision`, `packing_mode` opcional e `refresh` opcional |
| `GET /api/carts/{cart_id}/freight-quotes/{quote_reference}` | Consulta/revalida dados persistidos, sem chamar provedor |
| `POST /api/carts/{cart_id}/freight-quotes/{quote_reference}/selection` | `expected_revision`, `option_reference`; escolha local por snapshot |

Modo padrão `equal_volumes`: cada unidade é um volume com peso/medidas cadastrados; todas devem ter
a mesma geometria. Volumes divergentes retornam 422, sem pacote agregado inventado. O comprador pode
pedir explicitamente `packing_mode: "weight_only"` para estimativa sem cubagem; ela não fecha pedido.
Não se aceita preço, CEP, peso/dimensões ou empresa/unidade nesse POST: vêm do carrinho/catalog/config.

O servidor salva bytes canônicos/request_key antes de HTTP e os snapshots antes de responder.
Repetir os mesmos critérios retorna cotação persistida; timeout reusa os mesmos bytes/chave.
Mudança de carrinho/configuração ou `refresh: true` exige nova chave. Chamada concorrente em andamento
retorna 202 pending com a mesma referência, sem segundo HTTP; resposta tardia não revive cotação invalidada.
Cliente deve respeitar 409/refetch e Retry-After. `FREIGHT_INTEGRATION_SCOPE` é namespace local estável
da organização/ambiente, não seletor de tenant enviado à Packsenvios.

O navegador recebe apenas referências internas, preço, prazo, nome e flags. `manual_only` pode ser
escolhido **localmente** para a compra simulada, sem POST de seleção/contratação externo. Flags ausentes
continuam desconhecidas, exigindo revisão; não são inventadas como false. Cotação não reserva estoque.
Sem oferta e fiscal_review retornam lista vazia; não é gerado frete zero/fallback.

Carrinhos anônimos geram Quote ligado diretamente ao Cart; nenhuma identidade de cliente é fabricada.
O vínculo com CheckoutAttempt real será preenchido uma única vez no checkout posterior.
Reversão 0003 para 0002 exige dados compatíveis com os NOT NULL legados; snapshots opcionais/cotações
guest não são convertidos em nomes, flags ou clientes fictícios para permitir downgrade.
Política, consistência e evidências: `docs/architecture/quote-engine.md`.

## Shell frontend e design system (prompt 08)

React Router navega entre `/catalogo`, `/carrinho`, `/checkout`, `/pedidos` e `/diagnostico`;
`/` redireciona para catálogo e endereços desconhecidos têm recuperação. Header, navegação,
estados e footer são compartilhados. CSS usa tokens de cor/espaçamento, componentes responsivos,
foco visível, skip link e menu mobile com Escape. Não há fonte/imagem externa carregada.

TanStack Query compartilha/cacheia health/runtime, com cancelamento e retry manual. O cliente
frontend usa exclusivamente `/api/...` na mesma origem, não aceita hosts externos nem o grupo
Packsenvios `/api/v1/freight`, não envia Authorization e não segue redirects.
Zod valida respostas e formulário de CEP, descartando campos privados adicionais.

`GET /api/runtime` retorna **somente** `freight_mode` e `purchases_simulated=true`, sem abrir conexão
com provedor/banco. O badge vem dessa resposta, não de variável pública ou valor Mock inventado.
Enquanto carrega/falha, mostra modo pendente/indisponível. Real significa configuração backend,
não homologação ou oferta comprovada. Pagamento/compra permanecem locais e simulados.

O shell foi criado no prompt 08; catálogo/carrinho foram conectados no 09; o prompt 10 implementa
comprador/endereço, cotação local-orquestrada e escolha por referência de snapshot. Pagamento/pedido
simulados e pedidos permanecem para o 11. Diagnóstico usa apenas API local.

```text
# Lint, Vitest, typecheck/build frontend (incluídos em Check):
python scripts/dev.py frontend-check
# Testes de layout em navegador real:
python scripts/dev.py layout
```

`layout` usa Playwright headless; o canal é `msedge` no Windows e `chromium` no Linux/CI,
selecionável por `PLAYWRIGHT_BROWSER_CHANNEL`.
Screenshots/traces são gerados em `frontend/test-results/` e ignorados pelo Git.
Evidências e decisões: `docs/architecture/frontend-shell.md`.

## Frontend catálogo e carrinho (prompt 09)

Com PostgreSQL local migrado e `Seed` executado, `/catalogo` consulta produtos paginados reais da
API. Busca por nome/SKU e filtro disponíveis/esgotados são aplicados no servidor antes da paginação
(`GET /api/products?q=...&in_stock=true|false`). `/catalogo/{id}` mostra detalhes, preço, peso,
dimensões e quantidade; esgotado fica visível, mas não pode ser adicionado.

O primeiro adicionar cria um carrinho via POST `/api/carts`; abrir o carrinho vazio não cria registros.
Somente UUID validado é persistido em `localStorage` (`freight-lab.cart-id`), sem chave/credencial,
preço, subtotal ou endereço. Reabrir/recarregar consulta o carrinho no servidor. Referência inválida/
inexistente tem recuperação explícita; carrinho encerrado não é reaberto silenciosamente.

Mutações são serializadas, sem retry automático. Uma leitura fresca fornece expected_revision antes
de POST/PATCH/DELETE; só produto/quantidade/revisão são enviados. Não há preço/peso do cliente.
Não se atualizam itens/totais do cache otimisticamente: rascunho de quantidade é local, receipt
validado substitui o cache apenas após sucesso. Falha/conflito faz refetch de carrinho/catálogo,
exibe erro seguro e não reaplica a operação. Estoque insuficiente/inativos bloqueiam continuidade.

Totais em centavos, peso informativo e quantidades vêm da resposta do servidor; Zod verifica
coerência sem corrigir/fabricar valores. Imagens são ilustrações SVG, não fotos reais de produtos.
Checkout ainda é a base do próximo prompt; frete não é somado inventando preço zero.

Tests incluem jornada de navegador **real** → API FastAPI **real** → PostgreSQL local com schema
próprio e seed sintético, verificando adicionar/alterar/remover, reload, subtotal/peso e nenhuma
reserva. Esse teste roda em `Check` quando PostgreSQL, Node/dependências frontend e Edge estão disponíveis.
Em ambiente sem esses pré-requisitos, é SKIP explícito, não comprovação de browser.
Decisões/evidências: `docs/architecture/frontend-store.md`.

## Checkout e comparação de fretes (prompt 10)

O checkout combina `PUT /api/carts/{id}/checkout-details` (comprador/endereço local),
`POST /api/carts/{id}/freight-quotes` (orquestrador local do motor 07), GET da referência
interna e POST `/selection` local. A UI não chama rotas Packsenvios; o backend adapter concentra
o POST/GET externo documentado e mantém Bearer no servidor.

- Nome/e-mail/endereço/UF validados; CEP é string de oito dígitos preservando zeros.
- Cotação usa peso, medidas, valor, empresa/unidade e origem derivados/configurados no backend.
- Opções múltiplas exibem preço em centavos formatado, prazo em dias e flags manuais/demonstração.
  Identidade selecionada é UUID interno do snapshot; preço/IDs externos não são reenviados.
- No modo `equal_volumes`, medidas divergentes exigem revisão/embalagem. `weight_only` é estimativa
  explicitamente marcada, não selecionável para fechar pedido.
- `unavailable` e `fiscal_review` mostram estados vazios separados, sem preço zero.
- Mudar qualquer campo salvo do comprador/endereço altera a revisão e fingerprint do carrinho,
  invalida opção/cotação anteriores e oculta seleção até nova cotação.
- Comprar/pagar continua simulado e fora da ação de cotar/selecionar; nenhum pedido externo é criado.

Detalhes de estado, limites do contrato e evidência: `docs/architecture/checkout-freight.md`.

Checkout salva apenas comprador/endereço no carrinho local (sem identidade/documentos fiscais),
obtém revisão do servidor e chama o orquestrador interno. Seleciona `option_reference` local;
`request_key`, `data.id`, resposta JSON bruta e Bearer não são expostos. Flags desconhecidas exigem
revisão. Alterar dados após cotar oculta ofertas imediatamente, invalida a tentativa no backend e
uma nova cotação usa novo UUID. Resposta/local state não afirma contratação externa.

## Pagamento simulado e pedidos (prompt 11)

- `POST /api/carts/{cart_id}/orders`: corpo somente `{expected_revision, submission_key}`. Cria pedido
  local + `PaymentSimulation(simulation=true,status=pending)`. A chave é UUID própria da loja.
  Repetição idêntica retorna mesmo pedido; mesma chave com outro carrinho/revisão retorna 409.
- `POST /api/orders/{order_id}/confirm`: `{expected_cart_revision, outcome}` onde outcome é decisão
  explícita `pending|approved|declined` do **simulador local**, nunca um gateway financeiro.
- `GET /api/orders/{order_id}` e `GET /api/carts/{cart_id}/orders?page=1&page_size=20`: confirmação
  e histórico do carrinho UUID local.
- `POST /api/orders/{order_id}/cancel`: cancelamento local compensatório, somente antes de fulfillment
  avançar, com liberação idempotente das reservas ativas.

Pedido congela linhas/preços/produtos, endereço de envio e snapshot local selecionado. No modo aprovação
simulada, o servidor relê catálogo/carrinho/quote e opção sob locks, valida revisão, fingerprint, estoque
e soma antes de gravar pedido pago simulado, fulfillment local e reservas numa transação. Pending/declined
não reservam. Compra/pagamento são simulados; até seleção `manual_only` é somente vínculo local, sem
POST de seleção/contratação Packsenvios.

`frontend/src/api/orders.ts` e confirmação/histórico mostram `simulation=true` e guardam uma chave de
criação estável em sessionStorage por carrinho/revisão somente até sucesso; nunca guardam dados de
pagamento ou credenciais. Não há formulário de cartão/gateway. Esquema/reservas: revision 0005;
detalhes, compensação, testes e limitações em `docs/architecture/orders-simulation.md`.

Downgrade da revision 0005 é bloqueado quando há orders/payments/reservations, para não descartar
evidência local de idempotência/compensação inadvertidamente. Só em schema realmente vazio é reversível.

## Convenções e configuração

- Backend em `backend/src/freight_ecommerce`, app factory e schemas Pydantic; jsr-testrunner em `backend/tests`.
- Frontend TS strict, ESLint flat config, Prettier; Vitest/jsdom com testes junto aos componentes.
- Ruff compartilhado em `.ruff.toml`. Scripts de verificação transversal em `tests/`.
- Backend lê `.env` da raiz; variáveis de processo têm precedência. Configurações: `APP_ENVIRONMENT`
  e `DATABASE_URL` (armazenada como `SecretStr`, sem exposição pelo healthcheck).
- Vite usa apenas `VITE_*` públicos. Nunca colocar credencial Bearer em variável `VITE_*`.
- `FREIGHT_*` configuram somente o adaptador backend de cotação; conexão com carrinho no 07.
- `.gitignore` exclui `.env`, venvs, node_modules, builds e logs. `.dockerignore` exclui segredos do build.
- `manual_only: true` jamais habilita contratação automática; seleção de opção será vínculo local.
- Ler `docs/reference/gestao-frete-integracao-ecommerce-teste.md` antes da integração externa.
- Documentos de auditoria copiados são históricos; esta raiz efetiva supersede os caminhos anteriores.

## Estrutura

```text
.
├── .github/          # CI, dependency updates, issue/PR templates
├── backend/          # Poetry, FastAPI, Pydantic, jsr-testrunner
├── frontend/         # React, TypeScript, Vite, Vitest
├── tests/            # Smoke HTTP e conferência contratual
├── docs/             # arquitetura, desenvolvimento, testes, implantação, contrato e ADRs
├── infra/            # Dockerfiles e notas
├── scripts/dev.py    # ponto de entrada multiplataforma
├── scripts/dev.ps1   # wrapper PowerShell
├── scripts/dev.sh    # wrapper Bash
├── LICENSE           # MIT
├── ARCHITECTURE.md
├── CONTRIBUTING.md
├── SECURITY.md
├── SUPPORT.md
├── THIRD_PARTY_NOTICES.md
├── .env.example
├── .gitignore
└── docker-compose.yml
```

Evidências de execução e limitações: `docs/architecture/bootstrap-current-root.md`.

## Contribuição e licença

Leia `CONTRIBUTING.md` antes de abrir pull requests e `SECURITY.md` antes de reportar questões sensíveis.
Os contribuidores identificados pelo histórico Git estão em `CONTRIBUTORS.md`. O código do projeto é
distribuído sob a licença [MIT](LICENSE). A licença não concede direitos sobre a API, marcas, serviços
ou contrato de Packsenvios; veja `THIRD_PARTY_NOTICES.md`.
