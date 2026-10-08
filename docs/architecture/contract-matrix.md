# Matriz de contrato Packsenvios — freight-ecommerce-test

> **Fonte única de verdade:** `docs/reference/gestao-frete-integracao-ecommerce-teste.md` (contrato inspecionado em 08/10/2026, base `0e860f0bb24411baa1c6e55734ca7e631acc66a1`).
> **Status de verificação deste documento:** traçado por leitura da documentação e por conferência estática contra o snapshot local `packslogenvios` (commit `f9c8906b`, árvore de trabalho suja). **Nenhuma rota foi verificada por chamada HTTP real.** Não existe ambiente de homologação ativo assumido.
> Linhas citadas (`L##`) referem-se ao arquivo de referência acima.

## 1. Autenticação e contexto (L19–L27)

| Item | Valor do contrato |
|---|---|
| Header obrigatório | `Authorization: Bearer <chave>`, `Accept: application/json` |
| JSON | `Content-Type: application/json` |
| Upload | multipart montado pelo cliente (boundary próprio) |
| Escopo da organização | Vem da chave. **Proibido** enviar `workspace_id` / `shipper_account_id` como seletor de tenant (L23) |
| Contexto | `freight_company_id` e `freight_location_id` são UUIDs condicionais à resolução/autorização; respeitar vínculo fixo da chave. Empresa é obrigatória no upload. GET na query string, POST no corpo (ou query quando o corpo é reservado) (L25/L57–L58/L230) |
| Descoberta | **Não existe** endpoint Bearer de descoberta de empresa/unidade; UUIDs vêm do portal (Integrações) (L23) |
| Revalidação | Sanctum, usuário verificado, acesso ao produto, membership e permissões são revalidados no backend; ability correta pode receber `403` se o titular foi revogado (L19) |
| Chave | Emissão via portal com `freight.integrations.manage`; empresa obrigatória; unidade se existirem unidades ativas (L14). Substituição invalida a anterior; expiração nula ou até 90 dias (L16) |
| Checkout mínimo (recorte desta loja) | Abilities `freight:quotes:write` + `freight:quotes:read` **e** grants atuais do titular `freight.quotes.create` + `freight.shipments.read` (L15) |

## 2. Rotas Bearer de Frete — matriz completa (L33–L48)

Todas as rotas estão sob `BASE_URL` (sem sufixo `/api/v1/freight`, sem barra final). `{quote_request}`, `{shipment}` e `{batch}` são UUIDs; `{row}` é o número da linha retornado pelo lote (não índice de array).

| # | Método | Caminho | Ability da chave | Finalidade / limites (doc) | IDs envolvidos | Quota / limite | HTTP | Verificação |
|---|---|---|---|---|---|---|---|---|
| 1 | POST | `/api/v1/freight/quotes` | `freight:quotes:write` | Cotação simples ou replay; JSON de critérios; 200 mesmo sem ofertas (L35) | `request_key` (UUID estável, namespace por organização), `data.id` no retorno | Limiter geral 120 req/min por organização (L311) | 200 | Doc L35/L52–L180; OpenAPI local: **sim**; HTTP: **não** |
| 2 | POST | `/api/v1/freight/quotes/bulk` | `freight:quotes:write` | 1–20 linhas em transação; aborta tudo em erro (L36, L190) | `request_key` distinto por linha; `external_reference` ≤80 opcional | **3 req/min por organização** (L36, L311) | 200 | Doc L36/L190; OpenAPI local: **sim**; HTTP: **não** |
| 3 | GET | `/api/v1/freight/quotes/{quote_request}` | `freight:quotes:read` | Consulta cotação acessível; mesmo envelope da criação; sem corpo (L37, L148) | `data.id` (≠ `request_key`, ≠ pedido da loja) | Geral | 200 | Doc L37/L148–L157; OpenAPI local: **sim**; HTTP: **não** |
| 4 | POST | `/api/v1/freight/quotes/{quote_request}/selection` | `freight:quotes:select` | Seleção histórica elegível; `carrier_workspace_id` + `rate_table_id`; **recusa ofertas novas manuais** (L38, L194) | UUIDs da transportadora/tabela histórica | Geral | 200 | Doc L38/L192–L194; OpenAPI local: **sim**; HTTP: **não**. **Fora do recorte da loja** (L325) |
| 5 | POST | `/api/v1/freight/quotes/{quote_request}/contract` | `freight:shipments:write` **e** `freight:financial:read` | Contratação histórica; corpo multipart com XML fiscal; 200 pode ser `fiscal_review`; **não habilita ofertas manuais** (L39, L196–L212) | `shipment_id`, `shipment_code`, `quote_id` (≠ `data.id`), `payment_id` | Geral | 200 | Doc L39/L196–L212; OpenAPI local: **sim** (schema desatualizado, §5); HTTP: **não**. **Fora do recorte da loja** (L325) |
| 6 | GET | `/api/v1/freight/shipments` | `freight:shipments:read` | Envios históricos acessíveis; até 20/página; cursor opaco ≤500 chars (L40, L252) | `id` (UUID histórico), `code` (código público) | 20/página | 200 | Doc L40/L252–L254; OpenAPI local: **sim**; HTTP: **não** |
| 7 | GET | `/api/v1/freight/shipments/{shipment}` | `freight:shipments:read` | Resumo + até 20 eventos/página (L41, L254) | UUID histórico no caminho | 20 eventos/página | 200 | Doc L41/L254; OpenAPI local: **sim**; HTTP: **não** |
| 8 | POST | `/api/v1/freight/order-imports` | `freight:shipments:write` | Upload CSV/XLSX multipart (`file` + `freight_company_id`, unidade quando aplicável) (L42, L230) | `BATCH_ID` (`id` do 202); dedupe por conteúdo+organização+titular+empresa+unidade (L240) | Máx. **200.000 envios/arquivo**; HTTP **29.296 KiB**; leitor 30.000.000 bytes; XLSX ≤500 entradas ZIP / 300.000.000 bytes descompactados (L222); **10 arquivos pendentes** e **3 lotes** ativos por organização/titular → 429 (L228) | 202 | Doc L42/L214–L240; OpenAPI local: **não presente** (§5); HTTP: **não** |
| 9 | GET | `/api/v1/freight/order-imports/{batch}` | `freight:shipments:read` | Estado + até 50 linhas; `cursor` inteiro 0–1.048.576; `errors_only=1` (evitar literal `true`) (L43, L242) | `BATCH_ID`; itens: `row`, `shipmentId`, `publicCode`, `dispatchStatus`... (L242) | 50 linhas/página | 200 | Doc L43/L242; OpenAPI local: **não presente**; HTTP: **não**. Somente o titular criador (L240) |
| 10 | POST | `/api/v1/freight/order-imports/{batch}/confirm` | `freight:shipments:write` | `{"confirm_valid_rows": true}`; estados `review`/`confirming`/`imported` com ≥1 linha válida (L44, L243) | `BATCH_ID` | — | 202 | Doc L44/L243; OpenAPI local: **não presente**; HTTP: **não** |
| 11 | POST | `/api/v1/freight/order-imports/{batch}/resume` | `freight:shipments:write` | Retoma lote `failed`/`queued`/`parsing`/`confirming`; sem payload específico além do contexto (L45, L246) | `BATCH_ID` | — | 202 | Doc L45/L246; OpenAPI local: **não presente**; HTTP: **não**. **Não** reconcilia despacho `uncertain` |
| 12 | POST | `/api/v1/freight/order-imports/{batch}/dispatch` | `freight:shipments:write` | `{"connection_id": UUID, "confirm_dispatch": true}`; lote em `imported`, integralmente importado e sem inconsistências; conexão pronta (L46, L244) | `connection_id` (cadastro portal, sem descoberta Bearer); id da solicitação ≠ `BATCH_ID` (L267) | Repetição preserva solicitação; não troca conexão (L245) | 202 | Doc L46/L244–L245; OpenAPI local: **não presente**; HTTP: **não** |
| 13 | GET | `/api/v1/freight/order-imports/{batch}/rows/{row}/tracking` | `freight:shipments:read` | Snapshot de rastreio/etiquetas de linha aceita; não chama provedor; `Cache-Control: private, no-store` (L47, L256) | `row` = linha da planilha (normalmente ≥3) | — | 200 | Doc L47/L256; OpenAPI local: **não presente**; HTTP: **não** |
| 14 | POST | `/api/v1/freight/order-imports/{batch}/rows/{row}/tracking` | `freight:shipments:read` | Solicita atualização assíncrona Elite; sem payload específico além do contexto; `{"status": "queued"}` (L48, L256) | `row` + `BATCH_ID` | Dedupe **60 s** por lote/linha (compartilhado com portal); quotas do provedor continuam (L48) | 202 | Doc L48/L256; OpenAPI local: **não presente**; HTTP: **não** |

### Rotas explicitamente inexistentes (não inventar)

- Não há `POST /orders` JSON (importação é o único caminho Bearer de entrada de pedidos) (L216).
- Não há rotas REST JSON para comprar frete novo avulso, baixar etiqueta por rota própria, cancelar envio ou cadastrar webhook (L50).
- Não há endpoint financeiro em `freight:financial:read` (ability só habilita a contratação histórica) (L50).
- Não usar APIs Postagem/TMS como fallback de Frete (L50).
- Cadastro de webhooks é **por sessão de portal**, não Bearer (L273).

## 3. Schema da cotação simples (request) — L54–L71

| Campo | Obrig. | Formato / limites |
|---|---|---|
| `request_key` | Sim | UUID estável; idempotência dentro da organização; trocar em qualquer mudança de critérios (L186) |
| `freight_company_id` | Condicional | UUID empresa autorizada; vínculo da chave prevalece |
| `freight_location_id` | Condicional | UUID unidade ativa da empresa |
| `origin_postal_code` | Condicional | 8 dígitos; pode vir do cadastro da unidade; coerência é responsabilidade da loja (L27) |
| `destination_postal_code` | Sim | 8 dígitos, preservando zeros iniciais |
| `weight_kg` | Sim | **String** decimal, ponto decimal, 1–5 dígitos inteiros, até 3 casas; >0 e ≤50.000 kg |
| `declared_value_cents` | Sim | Inteiro 0–100.000.000 (valor da mercadoria, não do frete) |
| `length_cm`, `width_cm`, `height_cm` | Condicional | Inteiros 1–300 cm; uma dimensão exige as três **e** `volume_count`; sem dimensões → `weight_only`, não contratável |
| `volume_count` | Condicional | Inteiro 1–1.000; obrigatório com dimensões; dimensões agregadas = volumes **iguais** |
| `volumes` | Opcional | Array 1–1.000; por objeto: `weight_grams` (1–50.000.000 g), `length_cm`/`width_cm`/`height_cm` (1–300), todos obrigatórios. Soma dos gramas deve ser **exatamente** `weight_kg × 1000`; tamanho do array = `volume_count` (ou 1 se ausente) (L71) |
| `service` | Opcional/nulo | String ≤80; filtro conforme tabela |
| `modal` | Opcional/nulo | `rodoviario` \| `aereo` \| `maritimo` \| `ferroviario` |
| `distance_meters` | Opcional | Inteiro 1–10.000.000 |
| `invoice_count` | Opcional | 0–1.000; **somente** cotação simples; **proibido** nas linhas de bulk (L69, L190) |

Normalizações automáticas da cotação simples (apenas aqui): remove não numéricos do CEP e troca vírgula por ponto no peso (L73). O formato canônico acima deve ser enviado; **linhas de bulk não recebem essa normalização**.

`volumes` aceita somente os quatro campos declarados por objeto. Para cubagem, enviar também todas as dimensões agregadas e `volume_count`: volumes individuais não dispensam as condições de `weight_only`; o total continua limitado a 50.000 kg (L65/L71).

Bulk: `{"rows": [...]}` com mesmos critérios por linha, `request_key` distinto, `external_reference` opcional ≤80; retorno `items[]` com `row` (1–20), `externalReference`, `quoteRequestId`, `status`, `optionCount` (L190).

## 4. Schema da resposta / opções — L121–L180

Envelope: `{"data": {...}}`. Campos de `data`:

| Campo | Observação |
|---|---|
| `id` | UUID consultável em `/quotes/{quote_request}` (**não** é `request_key`) |
| `status` | `quoted` \| `unavailable` \| `fiscal_review` (sem snapshots: `unavailable` ou `fiscal_review`, nunca `quoted` com `options: []` — L121, L321) |
| `criteria` | Critérios persistidos/normalizados; **não** inclui `request_key`; pode trazer empresa/unidade resolvidas |
| `options[]` | Snapshots de `offer_snapshots`; **não existe `options[i].id` genérico** (L169); tabela pode gerar >1 opção por serviço; sem ordenação garantida (L180) |
| `selection` | Nulo em cotação nova manual; histórico: `price_snapshot_id`, `carrier_workspace_id`, `rate_table_id`, `price_cents` (L176) |
| `shipment_code` | Código histórico; **não** substitui UUID de `/shipments/{shipment}` (L177) |
| `created_at` | ISO 8601 ou nulo |

Os três estados acima descrevem a **criação nova**, não um enum fechado para a consulta histórica: GET pode refletir seleção/contratação posterior (L148, L196, L212). `manual_only`, `demonstration_only` e `weight_only` não devem ser inventados como estados desse enum; são condições/indicadores distintos.

Por opção: `price_cents` (inteiro), `deadline_days` (dias da tabela — não prometer dias úteis), `carrier_name`, `private_carrier_id`, `rate_table_id`, `matrix_version`, `freight_company_id`, `freight_location_id`, `manual_only`, `price_source` (`private_table` nas ofertas novas), `carrier_workspace_id` (`null` nas novas), `demonstration_only`, `assumptions`, `charged_weight_grams`, `cubage`, `price_components`, `calculation_snapshot`, `calculated_at`, `agreement_id`, `subscription_id`, `benefit_id` (nulos nas novas internas) (L163–L175).

Regras de apresentação: `options: []` = indisponibilidade ou revisão fiscal — **sem preço zero, transportadora inventada ou fallback** (L180). `manual_only: true` = informa preço/prazo mas **não** habilita seleção/contratação automática (L9, L194).

### 4.1 Schemas das demais operações (nomes preservados)

| Operação | Entrada / resposta documentada | Fonte |
|---|---|---|
| Seleção histórica | JSON com UUIDs `carrier_workspace_id`, `rate_table_id`. Resposta: `data.status: selected`, `price_snapshot_id`, `carrier_workspace_id`, `price_cents`; não fabricar envelope adicional | L194–L196 |
| Contratação histórica | Multipart; requisitos de remetente/destinatário, endereços, pacote e fiscal em L198–L210. Resultado: `data.status` (`contracted` ou `fiscal_review`), `shipment_id`, `shipment_code`, `carrier_workspace_id`, `quote_id`, `price_cents`, `payment_id`, `payment_status`; campos comerciais podem ser nulos | L196–L212 |
| Lista/detalhe de envios históricos | Lista: `items`, `pagination`. Detalhe: `shipment`, `events`, `pagination`. Paginação: `hasMore`, `nextCursor`, `perPage: 20`. Resumo: `id`, `code`, `carrierName`, `originPostalCode`, `destinationPostalCode`, `status`, `priceCents`, `deadlineDays`, `volumeCount`, `createdAt`, `recipientName`, `destinationLabel`, `trackingCode`. Evento: `id`, `status`, `title`, `description`, `occurredAt` | L252–L254 |
| Upload / resumo de lote | Multipart `file`, empresa obrigatória e unidade condicional. Resumo: `id`, `filename`, `status`, `total`, `valid`, `invalid`, `imported`, `duplicates`, `processed`, `issue`, `createdAt`, `canDelete`, `tmsAvailable`, `dispatch`. `canDelete` não cria rota DELETE | L230–L240 |
| Consulta de lote | Acrescenta na raiz `items`, `hasMore`, `nextCursor`. Item: `row`, `status`, `invoiceNumber`, `recipientName`, `destination`, `volumes`, `weightKg`, `errors`, `shipmentId`, `publicCode`, `dispatchStatus` | L242 |
| Confirmar / retomar | Confirmação: `confirm_valid_rows: true`; retomada sem payload específico além do contexto. HTTP 202. O guia não detalha um schema de resposta próprio completo para cada ação; manter lacuna explícita | L44–L45, L243/L246 |
| Despacho | JSON `connection_id` (UUID), `confirm_dispatch: true`. HTTP 202: `id`, `batchId`, `connectionId`, `status`, `total`, `enqueued`, `accepted`, `rejected`, `uncertain`, `issue` | L244–L245 |
| Tracking | GET: `code`, `reference`, `acceptedAt`, `updatedAt`, `issue`, `labels`, `labelsAt`, `events`; listas podem estar vazias. POST: `{"status":"queued"}`, HTTP 202. Estruturas internas completas de `labels`/`events` não são especificadas no guia | L256 |

### 4.2 Modelo de importação e lacunas de schema

- Modelo de portal por sessão: `/gestao-frete/{workspace_slug}/envios/importacoes/modelo`; `workspace_slug` não é UUID da empresa. Atual: 28 colunas, instrução linha 1, cabeçalho linha 2 e dados desde linha 3; versões 27/30 possuem regras próprias (L216).
- Ordem semântica das 28 colunas: número da nota, chave NF-e; nome/documento/telefone destinatário; CEP/rua/número/complemento/bairro/cidade/UF destinatário; volumes, itens, valor total, peso kg; nome/documento remetente; CEP/rua/número/complemento/bairro/cidade/UF remetente; altura/largura/comprimento cm (L218). **Grafia literal dos cabeçalhos não consta integralmente neste guia**: obter o modelo oficial antes de afirmar compatibilidade de exportação (TODO-IMPORT-TEMPLATE, prompt 13).
- Campos preenchidos até 180 caracteres, sem controles inválidos; complementos cobrados pelo upload. CPF/CNPJ e NF-e válidos, CEP 8 dígitos, UF brasileira; telefone destinatário 8–22 caracteres com DDD. Nota 1–999.999.999, volumes 1–1.000, itens 1–1.000.000, dimensões 1–300; peso positivo até 3 casas (L224–L226).
- Valor total da planilha em **reais** (até 7 dígitos inteiros e 2 casas), sem notação científica; converter para centavos no backend. Não inventar documentos fiscais para exportar (L227; prompt 13).
- TODO-SCHEMA-DETAIL (06/13/14/17): tipos completos de snapshots, `dispatch`, `labels`, eventos importados e respostas de confirm/resume não foram publicados integralmente no guia. Manter estrutura tipada conservadora e fixtures explicitamente sintéticas, sem atribuir enums ou campos externos não documentados. Grants exatos de titular para operações além da cotação também não são enumerados integralmente: confirmar autoridade atual, sem inventar permissões.

## 5. Lacunas e divergências OpenAPI

| # | Lacuna | Evidência |
|---|---|---|
| O1 | Schema OpenAPI de cotação **não lista `volumes`**, mas o request aceita e valida (soma de pesos/quantidade) — não rejeitar funcionalidade por codegen | Doc L319 |
| O2 | OpenAPI lista `invoice_count` na cotação simples; bulk **não aceita** nas linhas | Doc L320 |
| O3 | Exemplo gerado do portal combina `status: quoted` com `options: []`; comportamento real da Action: `unavailable`/`fiscal_review` | Doc L321 |
| O4 | Schema de contratação herda limites/formas de Postagem desatualizados (peso/dimensões/volumes maiores, `review_confirmed` obrigatório, DC-e) — não usar schema herdado para concluir suporte fiscal | Doc L322 |
| O5 | Serializer de envios inclui campos extras `recipientName`, `destinationLabel`, `trackingCode` além do schema; não depender de `additionalProperties: false` | Doc L323 |
| O6 | **Snapshot local** `packslogenvios/docs/contracts/openapi/v1.json` e `docs/routes/manifest.json` contêm apenas as **7 rotas** de quotes/shipments; as **7 rotas** de `/order-imports/*` e tracking **não existem** no código local (base local `f9c8906b` ≠ base documentada `0e860f0`, objeto ausente no repositório local). Contrato das rotas 8–14 é **somente o documento de referência** | Conferência estática 08/10/2026: `git cat-file` → bad object; `git show HEAD:routes/api.php` lista só quotes×5 + shipments×2 |
| O7 | OpenAPI do portal exige sessão autenticada e servidor relativo `/` — não é endpoint Bearer público nem domínio de produção | Doc L315 |
| O8 | Webhooks, empresas/unidades, conexões de despacho e modelo de planilha são operações de **portal**, sem API Bearer correspondente | Doc L23, L216, L244, L273 |

**Decisão derivada:** não gerar cliente a partir do OpenAPI local; criar tipos TypeScript/Pydantic **tipados** derivados do documento de referência, com fixtures sintéticas marcadas e TODOs rastreáveis para O1–O8.

## 6. IDs — identidades que nunca se confundem (L258–L267)

| Identificador | Uso exclusivo |
|---|---|
| `request_key` | Replay de criação de cotação; não é recurso consultável |
| `data.id` da cotação / `quoteRequestId` (bulk) | `/quotes/{quote_request}` |
| `shipment_id` histórico / `id` de `/shipments` | `/shipments/{shipment}` |
| `shipment_code` / `code` | Código público; não entra no caminho da rota |
| `id` do upload | `/order-imports/{batch}` (BATCH_ID) |
| `items[].row` | `/order-imports/{batch}/rows/{row}/tracking` (linha da planilha, normalmente ≥3) |
| `items[].shipmentId` do lote / `data.shipmentId` de webhook | Envio **nativo importado**; não usar em `/shipments/{shipment}`; manter associação lote/linha na loja |
| id da solicitação de despacho | Acompanhamento no campo `dispatch` do lote; ≠ `BATCH_ID` |
| `quote_id` do resultado de contratação | Não substitui `data.id` da cotação (L212) |
| Referência interna da loja para opção | Índice/snapshot escolhido, mantido pela loja; nunca IDs arbitrários do navegador (L169, L187) |

## 7. Quotas, limites e retentativas

| Limite | Valor | Fonte |
|---|---|---|
| Limiter geral | 120 req/min por organização Frete (configurável no ambiente); 429 com `message: Muitas requisicoes. Tente novamente em instantes.` e `error: rate_limited` | L311 |
| Bulk de cotações | 3 req/min por organização | L36, L311 |
| Importação — arquivos | ≤10 pendentes armazenados por organização/titular | L228 |
| Importação — lotes | ≤3 em `queued`/`parsing`/`confirming`; exceder → 429 | L228 |
| Upload | HTTP ≤29.296 KiB; leitor ≤30.000.000 bytes; XLSX ≤500 entradas ZIP, ≤300.000.000 bytes descompactados | L222 |
| CSV | ≤1.048.576 linhas, ≤64 células/linha; `;` ou `,`; UTF-8 ou Windows-1252 | L223 |
| Envios por arquivo | ≤200.000 | L222 |
| Shipments / eventos | 20 por página; cursor opaco ≤500 chars, reenviar intacto e codificado | L40–L41, L252 |
| Linhas de lote (GET) | Até 50 por página; `cursor` inteiro 0–1.048.576; `errors_only=1` | L43, L242 |
| Tracking refresh | 202 `queued`; dedupe 60 s por lote/linha | L48, L256 |
| Webhooks (saída do portal — informativo) | 8 tentativas/ciclo; timeouts 3 s conexão / 8 s resposta; 60 entregas/min por host; 300 por empresa; ≤20 subscriptions por empresa — **não** é quota Bearer | L284 |

Política de erro/retentativa (L286–L311):

- `200`: verificar `status` e `options`, não apenas HTTP.
- `202`: assíncrono aceito — acompanhar estado; nunca declarar conclusão.
- `401`: chave/validade — sem retry infinito.
- `403`: ability/grant/contexto — nunca trocar de tenant.
- `404`: ID/contexto inacessível (lote de outro titular, linha não aceita).
- `409`: estado incompatível — consultar e corrigir antes de repetir.
- `422`: validação/divergência de replay (`errors.request_key`: `Esta chave já foi usada com outra cotação.`)/bloqueio fiscal-comercial.
- `429`: respeitar `Retry-After`; capacidade de importação pode exigir gestão pelo portal.
- `503`: falha de storage/enfileiramento — consultar persistência antes de repetir; falha de rede/5xx **não prova** ausência de efeito.
- Replay idêntico devolve cotação persistida (não recalcula) (L186); após resposta incerta em operação financeira, **consultar estado** antes de repetir (L212); `uncertain` de despacho **nunca** reenvio cego (L246).

## 8. Pré-requisitos para modo real (L11–L17, L327–L339)

1. `BASE_URL` confirmada com o responsável do ambiente; HTTPS fora de ambiente local isolado.
2. Chave de Frete emitida no portal (empresa + unidade quando existir); abilities de cotação; grants ativos do titular.
3. Segredo no mecanismo de segredos do **backend** (nunca no navegador, URL, repositório, logs, analytics).
4. Empresa/unidade/transportadoras/tabelas **atuais** ativas e elegíveis; cobertura de CEP, vigência, pesos, serviço/modal, cubagem e gates fiscais definidos no ambiente.
5. Para importação/despacho: modelo de planilha do portal (28 colunas atuais), conexão empresarial configurada/testada/homologada, filas e jobs ativos — **não ativados na cópia inspecionada** (L248).
6. Webhooks: destino HTTPS público porta 443; segredo de assinatura independente da chave API; homologação externa explícita antes de afirmar entrega (L271–L273).

## 9. Webhooks (receptor local, não homologado) — L269–L284

| Item | Contrato |
|---|---|
| Eventos | `shipment.created`, `shipment.dispatch_updated`, `shipment.tracking_updated`, `shipment.labels_updated`; teste: `webhook.test` |
| Corpo mínimo | `version: 1`, `id`, `type`, `occurredAt`, `companyId`, `locationId`, `data` (`shipmentId`, `publicCode`, `dispatchStatus`) |
| Assinatura | `X-Packsenvios-Signature` = `v1=` + HMAC-SHA256 hex de `timestamp + '.' + corpo_exato` com segredo próprio; comparação em tempo constante |
| Timestamp | `X-Packsenvios-Timestamp`; janela recomendada de 5 min é **controle do receptor**, não garantia de validação da Packsenvios |
| Dedupe | Por `id` do evento; `X-Packsenvios-Delivery` repete o mesmo id em retries; eventos podem chegar repetidos/fora de ordem |
| Confirmação | HTTP 2xx após recebimento seguro; detalhes via consulta autorizada (o evento não traz etiqueta nem pedido completo) |

## 10. Pontos explicitamente NÃO verificados

- Nenhuma chamada HTTP foi realizada (nenhuma rota, quota, erro ou webhook executado em ambiente real).
- Configuração efetiva de rate limit do ambiente não foi medida (L311).
- Existência de oferta elegível, tabelas, transportadoras, conexões e filas em qualquer ambiente **não** foi confirmada.
- Migrations, jobs, webhooks e publicação da API no ambiente inspecionado **não** foram executados/ativados (L5, L248, L271).
- O snapshot local `packslogenvios` está em outra base e com working tree suja (422 arquivos deletados, incluindo `routes/*.php`); serve apenas como referência estática de leitura, corroborando as rotas 1–7 em `git show HEAD:routes/api.php`.
