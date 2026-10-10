# 11 — Pedido local e pagamento simulado

> **Registro histórico pré-prompt 19:** o comando pytest abaixo registra a rodada original; a suíte
> atual usa jsr-testrunner. Veja `docs/development-testing.md`.

Raiz do projeto: `E:\Softwares\joao\tests`. Fonte externa de cotação: referência local versionada;
este fluxo não implementa nem presume novos contratos Packsenvios.

## API da loja

| Método/caminho | Payload/retorno | Efeito |
|---|---|---|
| POST `/api/carts/{cart_id}/orders` | `{expected_revision, submission_key}`; 201 create / 200 replay | Order local payment_pending, PaymentSimulation pending |
| POST `/api/orders/{order_id}/confirm` | `{expected_cart_revision, outcome: pending\|approved\|declined}` | Resultado escolhido explicitamente no simulador local |
| GET `/api/orders/{order_id}` | OrderView, linhas, PaymentSimulation, fulfillment opcional | Confirmação local |
| GET `/api/carts/{cart_id}/orders?page=1&page_size=20` | `{items,total}` | Histórico local do carrinho, ordenado recent-first |
| POST `/api/orders/{order_id}/cancel` | `{expected_cart_revision}` | Compensação local pré-fulfillment e liberação de reserva |

Todas são rotas da loja. Nenhuma cria POST de order, payment, freight selection ou contract remoto.

## Transação de criação/idempotência

1. Trancar cart; pesquisar idempotency key da loja **antes** de rejeitar o carrinho já associado a um
   order. Fingerprint submission = SHA-256 canonical de cart UUID + expected revision. Replay com
   mesma key/cart/revision devolve snapshot original, mesmo após confirmação; reutilização divergente 409.
2. Conferir expected revision, estado/cart editável, estoque atual, buyer/endereço salvos e ausência de
   item problema. Obter quote/snapshot selecionados que pertencem a este cart, current fingerprint,
   namespace+mode backend e estado remoto `quoted`. Critérios derivados outra vez do catálogo;
   validar UUID/snapshot/preço relacionados em FK e preço original do snapshot.
3. Oferta manual/demonstrativa pode ser registrada no pedido **local** com `freight_review_required=true`;
   flags desconhecidas também exigem revisão. Não existe contração automática. `weight_only`, cotação
   vazia/revisada, snapshot de outro quote/carrinho, seleção ausente ou ref/preço alterados são recusados.
4. Criar Customer/Address locais do checkout real, CheckoutAttempt local, vincular Quote guest ao attempt
   único, congelar Order e OrderItems (preço, nome, SKU e medidas), manter seleção local por snapshot e
   criar PaymentSimulation com `simulation=true`, pending e chave derivada distinta. Cart permanece
   checkout_pending/edit bloqueado porque já existe Order. Total de produto/frete vem do servidor.
5. Commit atômico. Falha em qualquer constraint restaura tudo; Unique submission key e lock do cart
   serializam double-submit. Não envia documento fiscal, credencial, payload do comprador a Packsenvios.

Chave de payment simulation determinística e separada da submission key do pedido; identificadores
remotos não são reaproveitados como chaves da loja. E-mail já associado a outra identidade local em
cart diferente retorna conflito; o serviço não prova identidade nem associa contas automaticamente.

## Confirmação e reserva/compensação

- `pending`: order/payment permanecem pendentes, sem reserva.
- `declined`: order/payment finais simulados, sem reserva, Cart abandonado e attempt invalidated.
- `approved`: dentro da mesma transação, verificar expected revision do pedido, cart e fingerprint,
  snapshot do endereço e option/quote, produtos ativos, preço/medidas/SKU congelados e saldo atual.
- Bloquear inventory por UUID de produto em ordem determinística, verificar todo o conjunto, e só
  depois incrementar `reserved`, registrar uma linha `StockReservation(active=true)` por produto,
  aprovar PaymentSimulation e Order (`paid_simulated`), confirmar attempt, fechar Cart e criar
  Fulfillment (`pago_simulado`) + TrackingEvent `source=simulated`. Falha aborta a transação inteira.
- A mesma resposta final repetida é idempotente; resposta diferente após estado final 409. Duas compras
  competindo por saldo fazem uma transação esperar; a segunda relê saldo após lock e recusa se insuficiente.
- Cancelar apenas Order `paid_simulated` cujo fulfillment continua `pago_simulado`; locks nas reservas
  e inventories liberam cada uma uma vez, marcam released_at e registram evento simulado. Após picking /
  expedição/fulfillment, cancelamento automático é bloqueado. Payment aprovado permanece como registro
  da simulação; não é reembolso/gateway.

## Privacidade e UI

OrderView retorna shipping destination resumido (CEP/cidade/UF), não nome/e-mail/endereço completo.
`simulation=true` é exigido por check constraint em Order e PaymentSimulation. UI confirmation/history
indica “simulado”, oferta manual, total congelado e fulfillment local. Não exibe detalhes fiscais/cartão.
Idempotency key de browser é armazenada temporariamente em sessionStorage por cart+revision para retry
de rede do POST create; não é token de autorização nem dado financeiro. Após sucesso é removida.

## Migration 0005 e reversibilidade

Adiciona `orders.cart_revision`, `submission_fingerprint`, `cart_fingerprint`, unicidade do
PaymentSimulation por order e tabela de reservas compensáveis. Downgrade reverte somente em schema
descartável/teste e preserva Order/Payment; nenhuma migration foi executada em banco externo.
Teste de migração prova upgrade/check sem drift/downgrade/upgrade usando schemas aleatórios próprios.

## Evidência esperada

- Regressão PostgreSQL real local: creates/replays, duplo submit concorrente, total adulterado,
  estados pending/approved/declined, limite de estoque concorrente, alteração de preço/quote, cancel/
  compensation, histórico e transições inválidas.
- Frontend Vitest: outcomes simulados, loading/error e histórico.
- Browser real: checkout → order pending → aprovar → fulfillment local → cancelar/liberar → histórico.
- HTTP Packsenvios, gateway financeiro real, etiqueta ou despacho: **não fazem parte desta feature**.

## Evidências efetivamente executadas

Execução: 10/10/2026. Dependências existentes; nenhuma instalação adicional para a feature.

| Verificação | Resultado |
|---|---|
| `poetry run ruff format .`, `poetry run ruff check .`, `poetry check --lock` | PASS |
| `pytest tests/test_orders.py` PostgreSQL real loopback | **16 PASS**: idempotência/concorrrência, pending/approved/declined, reserva, revalidação, cancelamento, histórico e downgrade seguro |
| `dev.ps1 Check` | **258 PASS backend**, sem SKIP na rodada final |
| Vitest/Testing Library | **45 PASS** em 6 arquivos (checkout/order confirmation/history/simulação) |
| Playwright shell Edge | **5 PASS** (320/390/768/1280 e teclado) |
| Jornada browser/API/PostgreSQL em `test_store_browser.py` | PASS: pedido simulado, aprovação, fulfillment local, cancelamento compensatório e histórico |
| ESLint / Prettier / TypeScript / Vite build | PASS |
| `dev.ps1 Smoke` e verificação contratual | PASS; teste sem rede externa Packsenvios |
| `docker compose config --quiet`, `git diff --check` | PASS |
| PostgreSQL próprio remanescente | **0 processos** ao final |

Fixture de persistência executa PostgreSQL portátil 17.6 real em schemas aleatórios próprios; browsers
usam Uvicorn/Vite em loopback, Edge instalado e domínio/endpoints internos da loja. Nenhuma migration
foi aplicada fora dos schemas de teste, sem seed/limpeza de banco compartilhado.

### Comandos separados por gerenciador

Repositório confirmado: **`E:\Softwares\joao\tests`**; Poetry config é `backend/pyproject.toml` e
Node manifest é `frontend/package.json`. `dev.ps1 Check` agora delega explicitamente a
`BackendCheck` e `FrontendCheck`; os comandos nunca dependem de encontrar `package.json` no backend.

```powershell
$env:TEST_POSTGRES_BIN = 'C:\Users\jacks\AppData\Local\Temp\opencode\freight-domain-pg-20261008\pgsql\bin'
# Backend somente Python/Poetry, scripts partem da raiz e usam poetry -C backend
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\dev.ps1 BackendCheck
# Frontend somente Node/npm, script usa npm --prefix frontend
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\dev.ps1 FrontendCheck
# Agregador sequencial
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\dev.ps1 Check
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\dev.ps1 Smoke
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\dev.ps1 LayoutCheck
```

Durante esta sessão, um comando manual inicial tentou `npm run` com diretório de trabalho `backend/`;
falhou porque **esse diretório corretamente não possui `package.json`**. Erro emitido:

```text
npm error code ENOENT
npm error syscall open
npm error path E:\Softwares\joao\tests\backend\package.json
npm error errno -4058
npm error enoent Could not read package.json: Error: ENOENT: no such file or directory, open 'E:\Softwares\joao\tests\backend\package.json'
```

Não foi criado arquivo artificial nem alterada arquitetura/dependência para mascarar o engano. Os comandos
subsequentes usaram Poetry no backend e npm sob `frontend/`; verificação final com tarefas separadas passou.

## Limitações e próximo prompt

- Compra, pagamento e ordem continuam simulados e `simulation=true`. Sem gateway, charge real,
  contrato ou shipment Packsenvios. `manual_only` é só snapshot/decisão local, não contratação.
- A reserva é contador transacional local; criação concorrente/replay são serializados e cancelamento
  compensatório só ocorre pré-fulfillment. Reembolso real não existe; payment simulado aprovado permanece.
- Customer com mesmo e-mail em outra identidade local distinta é recusado; não há autenticação de cliente.
- Browser inclui dados exclusivamente sintéticos no schema PostgreSQL temporário; nenhum dado fiscal real.
- Docker Desktop daemon permanece indisponível nesta máquina; Compose validado, runtime Docker não executado.

**Próximo prompt desbloqueado: 12 — Painel administrativo e fulfillment.**
