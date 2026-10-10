# 12 — Painel administrativo e fulfillment local

## Contrato e fronteiras

O painel administra o fulfillment local dos pedidos da loja em `/admin/pedidos`. As rotas
`/api/admin/orders` reutilizam a proteção `X-Local-Admin-Key` do catálogo; exigem `LOCAL_ADMIN_KEY`,
ficam desativadas em `production` e não usam a credencial Bearer Packsenvios. A chave local é digitada
na tela e mantida somente em memória até sair da página.

Não há chamada Packsenvios nesta feature. `pronto_para_importacao` e `importacao_pendente` são etapas
internas de preparação, não confirmação de upload/importação externa. `expedido_simulado` e
`entregue_simulado` são eventos locais. O painel mantém `external_status` separado e nulo enquanto não
houver status externo armazenado/vinculado; não deriva status externo das etapas internas. O contrato
em `docs/reference/gestao-frete-integracao-ecommerce-teste.md` documenta os fluxos reais de cotação,
importação e tracking; não autoriza inferir contratação/despacho ou criar endpoints externos.

## Rotas e transições

- `GET /api/admin/orders?page=1&page_size=20&order_status=...&fulfillment_status=...`: lista filtrada.
- `GET /api/admin/orders/{order_id}`: detalhe, snapshots de endereço/produtos/oferta, status interno,
  status externo quando houver associação e timeline consolidada de auditoria/eventos.
- `POST /api/admin/orders/{order_id}/fulfillment`: recebe `expected_status` e `status`; aplica
  optimistic check e o grafo de transições local.

Sequência local principal: `pago_simulado` → `separando` → `embalado` → `pronto_para_importacao` →
`importacao_pendente` → `expedido_simulado` → `entregue_simulado`. `importacao_pendente` pode voltar
a `pronto_para_importacao` para correção local. A transição para expedição aqui continua simulada,
sem prova de despacho ou aceite de transportadora.

Cada mudança grava evento `TrackingEvent(source=simulated)` com snapshot explícito
`external_status=null` e `IntegrationAudit(operation=admin_fulfillment_transition, mode=mock)` que
preserva origem local, estado anterior/novo e correlação. A timeline mistura eventos simulados e
auditorias locais ordenados por timestamp, mantendo o campo de origem. O pedido/pagamento continuam
`simulation=true`; oferta `manual_only` permanece apenas vínculo/snapshot local.

## Verificação

- Backend PostgreSQL: transições permitidas, transição incompatível, optimistic conflict, filtros,
  autorização administrativa, snapshot manual e integridade/origem da timeline.
- Frontend: autenticação antes de consultar painel, renderização de snapshot/auditoria e envio somente
  do cabeçalho administrativo local; sem `Authorization`/Bearer.
