# 05 — Carrinho persistido e cálculo comercial

> **Registro histórico pré-prompt 19:** comandos pytest e resultados abaixo são da rodada original; a
> suíte atual usa jsr-testrunner. Veja `docs/development-testing.md`.

Raiz: `E:\Softwares\joao\tests`. Reutiliza Cart/CartItem e os modelos de checkout/cotação.
Fonte contratual: `docs/reference/gestao-frete-integracao-ecommerce-teste.md`, especialmente
L184–L188 (catálogo servidor, alteração de critérios, chave nova, snapshots e seleção local).
Não implementa rotas, payloads, status ou permissões adicionais Packsenvios.

## Contrato interno e persistência

- API local: criar/consultar carrinho, adicionar/alterar/remover itens e atualizar/limpar destino.
- Schemas Pydantic em `cart/schemas.py`; campos extras recusados. Não aceitar preço, peso, medidas,
  subtotal, contexto de empresa externa ou estado de checkout como autoridade do comprador.
- `expected_revision` inteiro positivo obrigatório em toda mutação (query string no DELETE).
- POST items soma unidades na linha já existente; PATCH define quantidade absoluta. Repetir
  requisição com revisão anterior retorna 409, evitando double-submit acumulativo silencioso.
- Quantidade 1–1000 por produto e até 100 produtos distintos: limites da **loja local**.
- Migration `0002_cart_commercial_context` adiciona somente destino JSONB e fingerprint SHA-256
  ao Cart, com checks; nenhum dado pessoal é gerado por seed. Existing rows iniciam com NULL.
- O destino é uma cópia pertencente ao carrinho anônimo; não altera Address/Customer de outro cliente.
  Vínculo com sessão/cliente definitivo ficará para etapas de frontend/checkout. Referência local é UUID.

## Cálculo e consistência

Uma consulta SQL associa itens, produtos e inventário num snapshot coerente. Cada preço/peso
é obtido do cadastro atual; subtotais/pesos de linha são multiplicados por quantidade usando
inteiros. Totais são a soma das linhas. Resposta inclui medidas **por unidade**, não inventa
dimensões de pacote agregado; política de embalagem/volumes pertence ao motor de cotação 07.

Produto inativo, ausência de inventário ou disponibilidade menor que quantidade gera problema
na linha. O item permanece consultável/removível, `checkout_ready=false`, e a cotação antiga
não fica reutilizável localmente. Totais nessas linhas são informativos, não aprovação de compra.
Disponibilidade é `on_hand - reserved`; a checagem é momentânea, não garantia de estoque futuro.

Carrinho vazio retorna subtotal/peso/quantidade zero e não está pronto para checkout. Isso é soma
do carrinho, **não** preço de frete zero como fallback. `has_current_quote` verifica apenas tentativa
local quoted/cotação received na revisão atual; não afirma elegibilidade, seleção ou contratação externa.
Carrinhos encerrados são consultáveis, mas sem edição ou nova aprovação de checkout; seus totais
informativos ainda derivam do catálogo. História do pedido usa os snapshots do próprio Order/OrderItem.

## Concorrência e reserva de estoque

Todas as consultas/sincronizações e mutações adquirem `SELECT ... FOR UPDATE` no Cart antes
de ler/revalidar a revisão. A versão otimista SQLAlchemy continua ativa. Duas alterações que
partem da mesma revisão têm apenas uma vencedora; outra recebe 409, sem perda silenciosa.
Um item de outro carrinho não é editável por associar seu ID a um cart_id diferente.
Commit ocorre antes de devolver resposta; exceção durante flush/commit desfaz alterações da unidade
transacional. Nenhuma atualização de Inventory é feita por estas operações.

**Política para confirmação (serviço do prompt 11):**

1. Adicionar ao carrinho, consultar, cotar ou simular pagamento pendente não reserva estoque.
2. Confirmar compra aprovada simulada deve revalidar carrinho/revisão, catálogo e snapshot de frete.
3. Na mesma transação, bloquear inventários em ordem determinística de product_id, validar saldo
   e reservar as quantidades ao congelar o pedido. Usar chave idempotente própria do pedido:
   replay não reserva novamente. Dois carrinhos não podem confirmar o mesmo saldo indisponível.
4. Falha desfaz toda a transação; recusa não reserva. Cancelamento elegível libera reserva em
   compensação transacional/idempotente, sem alterar os snapshots históricos.

Essa política é explícita e preparada pelos checks/versionamento de Inventory, mas o endpoint
de confirmação/reserva **não** foi antecipado nesta feature.

## Invalidação e histórico

Fingerprint interno canônico inclui produto/quantidade, preço, peso, dimensões, nome/SKU,
problema de disponibilidade e todos os campos do destino. Não é request_key externo nem tenant.
ID da linha e contador de disponibilidade que ainda atende a quantidade não entram na chave.

- Alterações efetivas de itens, quantidade ou destino: revisão +1 e invalidação atômica.
- No-op de quantidade/endereço: mesma revisão e mesma cotação, se os critérios permanecerem iguais.
- GET recalcula e persiste a revisão/invalidação caso critérios do catálogo tenham mudado.
  Nenhum novo frete é calculado nessa leitura; alteração de stock suficiente não invalida preço.
- Mutação com revisão antiga retorna `cart_revision_conflict`. Se o cliente tinha revisão atual mas
  o catálogo mudou, somente sincronização/invalidação é persistida; a alteração solicitada não é aplicada
  e retorna `cart_commercial_changed` para refetch. Esse 409 não esconde aplicação parcial de itens.
- Tentativas abertas passam a invalidated; cotações requested/received/failed passam a invalidated
  **localmente**, mesmo que uma tentativa antiga já estivesse invalidated.
- Critérios, request_key, ID externo, resposta e offer snapshots permanecem intocados. Status externo
  quoted não é falsificado como cancelado. Nova tentativa/cálculo no motor 07 exige chave nova (L186).
- Cart checked_out/abandoned, tentativa confirmed ou Order existente bloqueiam mutações e
  invalidações destrutivas do histórico. Não se reabre automaticamente carrinho após pedido.
- `manual_only`/demonstration/weight_only não habilitam contratação; nenhuma chamada externa foi feita.

TODO-QUOTE-CART-LOCK (07/11): motor de cotação e confirmação devem adquirir o mesmo lock de Cart,
comparar revisão/fingerprint antes de criar/usar tentativa e revalidar após resposta de HTTP demorada.
Não reviver um quote invalidated quando um worker antigo terminar. Estado local não substitui consulta
ou idempotência da API real. Fixtures de cotações neste teste são explicitamente sintéticas e parciais,
nunca apresentadas como chamadas HTTP verificadas.

## Verificações

Data: 08/10/2026. Bibliotecas já instaladas atenderam à feature; nenhum pacote adicional ou
alteração de lockfile foi necessário. Testes utilizaram PostgreSQL **17.6 real portátil**, não SQLite,
em schemas aleatórios próprios num cluster temporário de loopback iniciado/encerrado pela fixture.

| Comando / verificação | Resultado efetivo |
|---|---|
| `poetry run ruff format .`, `poetry run ruff check .` | PASS |
| `poetry check --lock` | PASS |
| `pytest tests/test_domain.py tests/test_smoke.py -q` (rodada inicial) | 15 PASS |
| `pytest tests/test_cart_api.py ... -x -q` (rodada inicial) | 31 PASS com PostgreSQL real |
| `dev.ps1 Check` com `TEST_POSTGRES_BIN` | **128 PASS backend**, sem SKIP ou warnings na rodada final |
| Carrinho, incluído acima | **43 PASS**: CRUD, merge, recálculo, manipulação, estados/IDs/snapshots, concorrência, endereço, revisão e rollback |
| Regressão, incluída acima | **85 PASS** das etapas anteriores |
| Migration 0002 | Upgrade → downgrade base → upgrade; Alembic check sem drift; SQL offline da reversão incluindo destino |
| ESLint / Prettier / TypeScript / Vite build | PASS |
| Vitest | **4 PASS** |
| Verificador contratual | PASS; 14 métodos/rotas/abilities/linhas e 3 exemplos JSON válidos; sem HTTP Packsenvios |
| `dev.ps1 Smoke` | PASS; processos FastAPI/Vite e proxy local inicializados/encerrados |
| `docker compose config --quiet` | PASS; não implica execução de containers |
| `git diff --check` | PASS |
| Conferência de processos PostgreSQL próprios ao terminar | **0** |

Comandos da verificação completa na raiz, após configurar binários locais:

```powershell
$env:TEST_POSTGRES_BIN = 'C:\Users\jacks\AppData\Local\Temp\opencode\freight-domain-pg-20261008\pgsql\bin'
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\dev.ps1 Check
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\dev.ps1 Smoke
```

Dos 128 testes, 104 são marcados PostgreSQL (43 carrinho + 35 catálogo + 26 persistência).
Reversão ocorreu apenas em schemas pertencentes aos testes; nenhum dado de ambiente externo
ou banco de aplicação compartilhado foi alterado. O único ajuste inicial de lint foi formatação
dos arquivos novos; todas as rodadas de testes executadas nesta etapa passaram.

## Limitações e próximo prompt

- Aplicar `dev.ps1 Migrate` no PostgreSQL local configurado para disponibilizar a 0002 no ambiente
  de desenvolvimento. Os dados das suítes foram isolados/descartados, não seeds do banco do usuário.
- Não foram implementados reserva/confirmar pedido, autenticação de cliente, embalagem agregada,
  adapter Packsenvios ou UI de carrinho; são etapas posteriores conforme escopo descrito.
- Runtime/build Docker não foram executados nesta etapa; a execução real comprovada da persistência
  foi PostgreSQL portátil e a configuração Compose foi validada separadamente.
- Não houve chamada HTTP Packsenvios, contratação automática, alteração de status remoto,
  pagamento real ou migration externa. Bearer permanece exclusivo do backend.

**Próximo prompt desbloqueado: 06 — Cliente Packsenvios e configuração segura.**
