# 15 — Receptor de webhook local (não homologado)

## Fronteira e configuração

O receptor interno é `POST /api/webhooks/packsenvios`. Ele não cadastra, testa nem altera uma
subscription no portal, não faz chamadas de saída e não usa o Bearer de Frete. A chave de assinatura
é independente e server-only: `PACKSENVIOS_WEBHOOK_SECRET`. A empresa/unidade esperada vem das
configurações locais `FREIGHT_COMPANY_ID`/`FREIGHT_LOCATION_ID`; eventos de outro contexto são
rejeitados e os IDs do evento nunca selecionam tenant.

**TODO-CONTRACT:** a referência não especifica a sintaxe/unidade de
`X-Packsenvios-Timestamp`. O adaptador local tem somente o parser sintético `unix_seconds`; o receptor
permanece desabilitado se `PACKSENVIOS_WEBHOOK_TIMESTAMP_FORMAT` não estiver configurado. Confirme o
formato numa entrega de homologação antes de ativar essa configuração em ambiente de recebimento real.
Nenhuma entrega externa foi testada. `localhost` não é destino aceito para uma subscription real;
homologação exige destino público HTTPS/443 autorizado.

## Verificação e recepção durável

1. O endpoint lê o stream HTTP uma vez, preserva os bytes recebidos e assina/verifica esses bytes sem
   reserializar JSON. O limite de 1 MiB é uma proteção local do receptor, não limite do provedor.
2. Exige `X-Packsenvios-Timestamp` e `X-Packsenvios-Signature`; valida `v1=` + HMAC-SHA256 hexadecimal
   de `timestamp + '.' + body`, com `hmac.compare_digest`. A janela local recomendada é ±300 segundos.
3. Só depois da assinatura valida o envelope versionado e os tipos/eventos descritos na referência.
   `X-Packsenvios-Delivery`, se presente, precisa coincidir com o `id` assinado.
4. `webhook_receipts` tem unicidade por event `id`, SHA-256 do corpo exato e o payload tipado. Uma
   repetição idêntica devolve 200 sem segunda notificação; mesmo `id` com corpo diferente devolve 409.
5. O commit acontece antes de qualquer 2xx. Evento novo responde 202 com `reconciliation_pending`.
   Worker ausente/falho deixa o recibo persistido, registra `worker_status` e continua pendente; não
   afirma processamento. `/api/admin/webhooks/receipts` lista recibos para revisão local.

`occurredAt` anterior ao maior evento já recebido para a mesma empresa/envio marca
`out_of_order=true`; ambos são persistidos e nenhum estado atual é sobrescrito pelo evento. O webhook
é somente um sinal de mudança. O fluxo autorizado localiza o lote/linha e consulta a API de importação
ou tracking para reconciliar o snapshot atual; não há query por `shipmentId` no contrato, portanto o
receptor não inventa essa associação nem conclui reconciliação automaticamente.

## Reconciliação e segurança

Eventos de tracking/labels não contêm etiqueta nem pedido completo. Receipts não criam Order,
Fulfillment, tracking simulado, despacho ou entrega. `shipmentId`, `publicCode` e `dispatchStatus`
permanecem sinais externos do envelope. Não há URL de download ou outbound webhook no app.

## Testes e limitações

Fixtures de assinatura/body e IDs são explicitamente sintéticas. Cobrem assinatura válida/inválida,
bytes exatos, timestamp vencido, conflito/replay de ID, delivery ID, evento invertido, contexto,
persistência antes do 202 e indisponibilidade do notifier. Os testes usam PostgreSQL em schemas
efêmeros; não houve subscription, entrega, HTTPS público, worker ou homologação externa.
