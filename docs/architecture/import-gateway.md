# 13 — Preparação de CSV/XLSX e gateway de importação

## Contrato aplicado

Fonte: `docs/reference/gestao-frete-integracao-ecommerce-teste.md`, seções “Importação CSV/XLSX” e
“Consulta, rastreamento e IDs distintos”. O gateway implementa somente as rotas documentadas:

- `POST /api/v1/freight/order-imports`: multipart `file`, `freight_company_id` obrigatório e
  `freight_location_id` quando configurado/aplicável; resposta 202.
- `GET /api/v1/freight/order-imports/{batch}`: `freight_company_id`, unidade configurada, cursor
  inteiro e `errors_only=1` na query; 50 linhas por página.
- `POST /api/v1/freight/order-imports/{batch}/confirm`: query de contexto e JSON exato
  `{"confirm_valid_rows":true}`; só após consentimento local explícito e revalidação externa.

Não há rota JSON de criação de pedido, `/resume`, `/dispatch`, tracking Elite ou ação de contratação
nesta feature. O Bearer e o contexto vêm somente da configuração do backend. Rotas internas locais
exigem `X-Local-Admin-Key`, e upload só é habilitado em modo real. A API externa continua autoridade
para ability `freight:shipments:write`/`freight:shipments:read`, titular criador, estado e quotas;
401/403/404/409/422/429 são propagados sem retry de POST. O gateway não chama rede em modo mock.

## Arquivo e limites

A entrada aceita CSV (`text/csv`, `application/csv`, `application/vnd.ms-excel`) ou XLSX com MIME
OOXML, até 29.296 KiB. CSV verifica encoding UTF-8/Windows-1252, separador `,`/`;`, instrução na
linha 1, 28 células de cabeçalho na linha 2, dados desde a linha 3, limites estruturais e campos
fiscais/documentos/CEP/UF descritos na referência. XLSX verifica ZIP, até 500 entradas e 300 MB
descompactados; validação de células, worksheet e conteúdo fiscal continua no leitor externo. Nenhum
valor fiscal é inferido ou gerado.

## Exportação local bloqueada (TODO de contrato)

**TODO-CONTRACT:** obter, por fluxo autorizado do portal, o arquivo oficial atual para fixture local
versionada ou receber da fonte de contrato o texto exato da instrução da linha 1 e os 28 cabeçalhos
na grafia/ordem oficiais. A referência descreve somente os significados e a ordem, não os literais;
`backend/` não contém CSV/XLSX modelo. Além disso, pedido local não possui número/chave NF-e nem
documentos/telefone fiscais necessários de destinatário e remetente. Por isso `/export-readiness`
retorna `can_export=false` e pendências, e a UI não oferece download que possa parecer importável.
O arquivo sintético dos testes usa cabeçalhos explicitamente marcados `synthetic_fixture`; não é
compatível com upload real nem uma amostra de contrato.

## Persistência e processamento assíncrono

`ShipmentImportBatch` persiste `external_batch_id` separado da PK local, organização/configuração,
fingerprint SHA-256, referência opaca do bearer configurado, contexto company/location, estado externo
e contadores. Upload repetido com o mesmo conteúdo/contexto retorna o lote persistido; também respeita
a deduplicação externa documentada por conteúdo/organização/titular/empresa/unidade. Upload/confirm são
chamadas únicas; resposta incerta não dispara retry automático. Consulta atualiza `external_status` e
estado local sem converter `queued`, `parsing`, `review`, `confirming` ou `imported` em expedição.
Cada operador precisa consultar explicitamente o lote e marcar revisão antes do confirm; após HTTP 202,
a UI informa pendência e exige consulta posterior. Não há worker/fila ativado localmente.

## Testes

Fixtures externas são sintéticas e usam `httpx.MockTransport`; nenhuma chamada HTTP à Packsenvios foi
executada. PostgreSQL dos testes usa schemas aleatórios efêmeros. Não houve migration nem envio real.
