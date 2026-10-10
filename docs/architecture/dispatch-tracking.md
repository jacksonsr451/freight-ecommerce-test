# 14 — Despacho e rastreamento de lotes importados

## Rotas externas implementadas

Fonte única: `docs/reference/gestao-frete-integracao-ecommerce-teste.md`.

- `GET /api/v1/freight/order-imports/{batch}` com contexto company/location, cursor e
  `errors_only=1` continua sendo a consulta/reconciliação autoritativa do lote e do objeto `dispatch`.
- `POST /api/v1/freight/order-imports/{batch}/dispatch` usa somente o JSON documentado
  `{"connection_id":"...","confirm_dispatch":true}` e resposta HTTP 202 com `id`, `batchId`,
  `connectionId`, `status`, contagens e `issue`.
- `GET /api/v1/freight/order-imports/{batch}/rows/{row}/tracking` consulta snapshot real. `{row}` é
  o número da planilha (`items[].row`), não índice de array.
- `POST` no mesmo caminho não leva payload; resposta 202 `{"status":"queued"}`. A janela local de
  60 segundos por lote/linha complementa a deduplicação compartilhada com o portal, que segue
  autoridade final.

Todos os pedidos usam somente o backend para Bearer e company/location. A UI recebe apenas respostas
internas protegidas por `X-Local-Admin-Key`. A conexão de despacho é um UUID de configuração
backend `FREIGHT_DISPATCH_CONNECTION_ID`, fornecido pelo operador após setup externo; não há descoberta
ou cadastro de conexões por Bearer. A API externa revalida ability, titular do lote e conexão ativa,
testada e homologada. O modo mock nunca emite essas operações.

## Gate, deduplicação e estados

O endpoint local exige confirmação explícita do operador. Antes do POST externo, consulta novamente o
lote e exige `status=imported`, `imported=total`, `processed>=total`, `invalid=0` e `total>0`; a
conexão precisa estar configurada no backend. Se falta conexão ou lote completo, nenhuma chamada de
despacho ocorre. O gateway não envia `/resume`, nem cria order JSON.

Cada POST dispatch é one-shot. HTTP 202 mantém o estado local `dispatch_pending` e persiste request ID
e estado externo em campos separados; `enqueued` não vira `accepted`, e nenhum deles vira expedição ou
entrega. O detalhe exibe enqueued/accepted/rejected/uncertain sem converter isso em status de pedido.
Timeout, resposta 202 inválida ou contagem `uncertain` bloqueiam novo POST. O operador pode consultar
GET do lote para reconciliar `dispatch`; se a projeção continuar ausente/incerta, a UI exige reconciliação
pelo fluxo autorizado existente e não reenvia cegamente. Não se infere uma enumeração de estados além
dos valores efetivamente retornados.

Tracking GET armazena o snapshot retornado como auditoria `source=packsenvios`, associado ao ID do lote
e ao número original da linha. Eventos/labels são preservados na ordem recebida, sem misturar com
fulfillment/pagamento simulado da loja. O snapshot é exibido como dados, sem fabricar link de etiqueta,
download, aceite ou entrega. Refresh é uma solicitação assíncrona; `queued` não substitui o snapshot nem
afirma que houve atualização.

## Testes e limites de execução

Fixtures sintéticas verificam conexão ausente, gate de importação incompleta, confirmação local,
resposta 202 enfileirada, uncertain sem retry, request ID reconciliado, linha planilha, cache privado,
refresh e throttle, snapshot de tracking fora de ordem e ausência de falsa entrega. Transporte externo
usa exclusivamente `httpx.MockTransport`; nenhum Bearer real, API Packsenvios, conexão empresarial,
despacho ou atualização Elite foi chamado. Nenhuma migration é necessária: são reutilizadas as colunas
de despacho do lote e os registros `IntegrationAudit` existentes. Filas/workers externos continuam
sendo responsabilidade do ambiente autorizado; o gateway não tenta simular sua execução.
