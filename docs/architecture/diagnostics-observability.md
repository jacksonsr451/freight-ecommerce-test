# 16 — Diagnóstico e observabilidade segura

## Dados do painel e exportação

`GET /api/diagnostics` é uma leitura interna da loja com `Cache-Control: no-store`. Mostra o modo
público configurado, saúde da API e `SELECT 1` do PostgreSQL com latência local, disponibilidade de
configuração (booleanos), contagens pendentes e as 50 auditorias mais recentes. A tela exibe
correlation ID, operação, `request_key`, quote ID local/externo, status HTTP, latência, erro
normalizado e `Retry-After` persistido. O relatório JSON de exportação usa exatamente esse DTO.

O endpoint não instancia chamada externa nem mede disponibilidade Packsenvios; `external_api` fica
`not_checked`. Workers/filas sem healthcheck ficam `not_configured`/`not_observable`. Compras e
pagamentos permanecem `simulation=true`.

## Redação

O DTO é construído por allowlist a partir de `IntegrationAudit`; não serializa `details` inteiro,
request/response body, dados de cliente/endereço, documentos, `Authorization`, API key, segredo de
webhook, URL base nem conexão de despacho. Campos como snapshot real de tracking viram apenas
metadados redigidos (presença e contagem de eventos/labels). O snapshot detalhado pode ser consultado
somente no fluxo administrativo de importação, não neste relatório. Erros de banco são reduzidos a
`database_unavailable`; mensagem SQL/URL/credenciais não são entregues.

Logs do cliente de frete são campos estruturados (correlation ID, operação, tentativa, outcome, HTTP e
Retry-After) sem payload/headers. O correlation ID da auditoria da cotação é propagado ao logger; os
fluxos de importação geram/reutilizam o ID gravado em auditoria. O filtro de transporte continua
redigindo eventos internos do httpx/httpcore sem alterar logs de outros subsistemas.

## Evidência e limites

Testes verificam resposta de auditoria contendo IDs/status necessários, redaction de fixtures com
Bearer/documento/email e corpo de tracking, timeout/rede simulados com correlation ID, erro de banco
normalizado e export JSON sem segredos. Todos usam fixtures e transportes sintéticos; não há probe
externo nesta tela e exportar o relatório não equivale a homologação.
