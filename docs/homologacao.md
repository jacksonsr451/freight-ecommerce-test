# Roteiro de homologação controlada

## Estado atual

O repositório está funcional para testes locais e fixtures sintéticas. **Não está homologado com
Packsenvios nem com transportadora.** Nenhuma chamada HTTP real, importação, confirmação, despacho,
refresh Elite, entrega de webhook ou deploy foi executado por este roteiro. O pagamento/pedido continua
local e simulado.

## Pré-requisitos autorizados

Confirme com o responsável do ambiente antes de habilitar `FREIGHT_MODE=real`:

- `FREIGHT_BASE_URL` da aplicação autorizada, HTTPS fora de loopback, sem sufixo `/api/v1/freight`.
- `FREIGHT_API_KEY` no mecanismo de segredos do backend, nunca em `VITE_*`, navegador, URL, logs ou
  export de diagnóstico. Cotação requer `freight:quotes:write` e `freight:quotes:read`; o titular
  também precisa dos grants atuais `freight.quotes.create` e `freight.shipments.read`.
- `FREIGHT_COMPANY_ID` autorizado e `FREIGHT_LOCATION_ID` quando aplicável; não descubra nem escolha
  tenant por payload do navegador.
- Tabelas/transportadoras atuais, elegibilidade, cobertura, vigência e gates fiscais confirmados.
- Para import: chave com ability documentada `freight:shipments:write` e `freight:shipments:read`,
  título criador do lote, modelo oficial obtido pelo portal e filas/jobs externos ativos.
- Para dispatch: conexão da empresa criada/configurada/testada/homologada no portal; informar apenas
  o UUID existente em `FREIGHT_DISPATCH_CONNECTION_ID`. O backend não descobre nem cria conexões.
- Para webhooks: subscription criada no portal com `freight.integrations.read/manage`, destino público
  HTTPS porta 443 e segredo de assinatura independente em `PACKSENVIOS_WEBHOOK_SECRET`. Confirmar com
  o provedor a unidade de `X-Packsenvios-Timestamp`; o parser local `unix_seconds` é fixture sintética
  e o receptor fica desabilitado sem configuração explícita.

## Sequência e fronteiras

1. Rode `python scripts/dev.py env-check`, `python scripts/dev.py check`, `python scripts/dev.py smoke`
   e `python scripts/dev.py compose-smoke` em ambiente local autorizado antes de qualquer teste externo.
2. Comece com cotação/consulta apenas. Verifique `manual_only`, `demonstration_only`, contexto e
   snapshots. Oferta manual/demonstrativa só pode ser vínculo local, nunca contratação automática.
3. Para import, use arquivo sintético copiado do modelo oficial obtido no portal. O repositório ainda
   não exporta modelo compatível: a referência não contém a instrução literal da linha 1 nem a grafia
   integral dos 28 cabeçalhos. Revise linhas/rejeições, confirme somente após validação explícita e
   trate HTTP 202 como pendente.
4. Para dispatch, confirme lote `imported`, importação integral, sem inconsistências e conexão pronta.
   `enqueued` não significa `accepted`; `uncertain` exige reconciliação no fluxo autorizado, sem retry
   cego. Entrega real nunca é inferida de um estado local.
5. Para tracking, use `BATCH_ID` e `items[].row` (número original da planilha). GET lê snapshot;
   POST refresh 202 significa `queued`, não atualização pronta. Não invente etiqueta/download.
6. Para webhook, teste só após receber a subscription e segredo autorizados. O endpoint local deduplica
   por `id`, persiste antes do 2xx e marca mudanças como `reconciliation_pending`; compare estado real
   via consulta autorizada. Não interprete callback como aceite/entrega.

## Evidência

Registre por separado: local mock, HTTP real, processamento assíncrono, aceite de transportadora,
tracking/labels e entrega. Salve códigos HTTP, correlation IDs, request keys e horários sem guardar
Bearer, segredo HMAC, corpos sensíveis, CPF/CNPJ ou endereço. O relatório local `/api/diagnostics`
não executa probe externo e a exportação é redigida.
