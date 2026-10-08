# Gestão de Frete: integração de um ecommerce de teste

## Objetivo e alcance

Este guia permite construir uma loja de teste que consulta o frete no checkout pela API da Packsenvios. Descreve o contrato encontrado no checkout local em 08/10/2026, na base `0e860f0bb24411baa1c6e55734ca7e631acc66a1`, incluindo alterações locais preexistentes. Não confirma publicação, domínio público, homologação de transportadora ou execução em ambiente externo.

O fluxo é **navegador → backend da loja → API Packsenvios**. O navegador envia os dados do carrinho ao backend da loja; o backend valida produtos, peso, dimensões, valor e destino, consulta a Packsenvios e devolve somente as informações necessárias ao cliente. A chave Bearer fica exclusivamente no backend: nunca em JavaScript público, armazenamento do navegador, URL, repositório, analytics ou logs. A API documentada não oferece embed/iframe de checkout.

Cotar não cria pedido na Packsenvios, envio, pagamento ou etiqueta. As novas ofertas de transportadoras internas têm `manual_only: true`: podem informar preço e prazo na loja, mas não habilitam seleção/contratação automática pela rede. A escolha de uma opção no pedido da loja é um vínculo mantido pela própria loja. O fluxo separado de importação de pedidos por arquivo é descrito adiante.

## Preparação do ambiente e da chave

1. Obtenha com o responsável do ambiente a URL base da aplicação e confirme que o backend da loja consegue acessá-la. Não há domínio ou disponibilidade pública garantidos por este guia. `BASE_URL` significa essa URL base, sem o sufixo `/api/v1/freight` e sem barra final; use HTTPS ao transmitir credenciais fora de um ambiente local isolado.
2. Na Gestão de Frete, abra **Integrações**, selecione a empresa/unidade autorizada e emita uma chave pessoal de Frete. O titular precisa de acesso atual ao produto e de `freight.integrations.manage` para emissão; somente permissões que ele já possui podem ser atribuídas. Empresa é obrigatória na emissão atual. Se a empresa possui unidades ativas, selecione uma unidade; se não possui, não crie unidade fictícia.
3. Para um checkout que apenas cota e consulta a cotação, atribua `freight:quotes:write` e `freight:quotes:read`. Não são necessárias permissões de contratação, financeiro ou importação. O titular precisa também dos grants atuais correspondentes: `freight.quotes.create` e `freight.shipments.read`.
4. Guarde a chave no mecanismo de segredos do backend. O valor completo aparece apenas ao emitir/substituir. Substituição invalida a chave anterior; revogação interrompe seu uso. É possível emitir sem expiração ou com data futura de até 90 dias e alterar a validade de chave ativa. Chave expirada exige nova emissão.
5. Prepare empresa, unidade quando existente, transportadoras internas vinculadas e tabelas atuais ativas/elegíveis. Cobertura de CEPs, vigência, faixas de peso, serviço/modal, cubagem e condições fiscais influenciam as ofertas. Uma tabela demonstrativa não comprova condição comercial para cobrança.

Use `Authorization: Bearer <chave>` e `Accept: application/json` em todas as chamadas abaixo. Para JSON, acrescente `Content-Type: application/json`; para upload, deixe o cliente montar o boundary multipart. Chaves da Postagem/TMS e sessão do portal não substituem a chave nativa de Frete. Autenticação Sanctum, usuário verificado, acesso ativo ao produto, membership e permissões atuais são revalidados no backend; uma chave com a ability correta pode receber `403` se o acesso atual tiver sido revogado.

### Empresa e unidade não concedem autoridade

A organização vem da chave. Não envie `workspace_id`, `shipper_account_id` ou outro seletor de tenant para tentar mudar esse contexto. `freight_company_id` e `freight_location_id` são UUIDs dos cadastros autorizados de Frete, disponíveis no portal/Integrações; não há endpoint Bearer de descoberta de empresas/unidades nesta API.

Chaves novas vinculadas devem usar a mesma empresa/unidade em cada chamada; o middleware aplica esse vínculo e rejeita seleção diferente. Chaves anteriores sem vínculo continuam sujeitas ao acesso atual do titular. Com múltiplas empresas ativas, selecione a empresa explicitamente. Sem autorização de leitura consolidada e com múltiplas opções, selecione empresa e unidade. Em GET, envie esses campos na query string; em POST, no corpo, ou na query string quando o corpo for reservado a outro contrato. Eles também delimitam o recurso consultado, não apenas a criação.

A unidade deve estar ativa e pertencer à empresa. Se a origem for omitida, a cotação usa o CEP cadastrado da unidade; sem unidade explícita pode resolver a única unidade ativa autorizada. Com origem explícita, esse CEP não é automaticamente comparado ao cadastro: cabe à loja manter a origem coerente. Sem unidade e sem origem resolvível, a chamada falha. Empresa sem unidades pode cotar com origem explícita. Os vínculos/grants atuais são conferidos também no processamento assíncrono.

## Todas as operações Bearer de Frete

Todos os caminhos da tabela começam na raiz da URL base. `{quote_request}`, `{shipment}` e `{batch}` são UUIDs; `{row}` é o número da linha retornado pelo lote. As permissões são abilities da chave, cumulativas com os grants atuais do titular.

| Método | Caminho | Permissão da chave | Finalidade e limites |
|---|---|---|---|
| POST | `/api/v1/freight/quotes` | `freight:quotes:write` | Cotação simples ou replay; JSON de critérios; HTTP 200, inclusive sem ofertas. |
| POST | `/api/v1/freight/quotes/bulk` | `freight:quotes:write` | Cotar 1–20 linhas em transação; 3 chamadas/minuto por organização; HTTP 200. |
| GET | `/api/v1/freight/quotes/{quote_request}` | `freight:quotes:read` | Consultar a cotação acessível; mesmo envelope da criação; HTTP 200. |
| POST | `/api/v1/freight/quotes/{quote_request}/selection` | `freight:quotes:select` | Seleção histórica elegível; UUIDs `carrier_workspace_id` e `rate_table_id`; ofertas novas manuais são recusadas. |
| POST | `/api/v1/freight/quotes/{quote_request}/contract` | `freight:shipments:write` **e** `freight:financial:read` | Contratação histórica elegível, envio completo e gates fiscais; HTTP 200 pode ser `fiscal_review`. Não habilita ofertas manuais. |
| GET | `/api/v1/freight/shipments` | `freight:shipments:read` | Lista de envios históricos acessíveis; até 20 por página; cursor opaco de até 500 caracteres. |
| GET | `/api/v1/freight/shipments/{shipment}` | `freight:shipments:read` | Resumo histórico e até 20 eventos normalizados por página; cursor de até 500 caracteres. |
| POST | `/api/v1/freight/order-imports` | `freight:shipments:write` | Upload CSV/XLSX multipart, empresa obrigatória, unidade quando aplicável; HTTP 202. |
| GET | `/api/v1/freight/order-imports/{batch}` | `freight:shipments:read` | Estado e até 50 linhas do lote do próprio titular; cursor inteiro 0–1.048.576 e `errors_only` booleano opcionais. |
| POST | `/api/v1/freight/order-imports/{batch}/confirm` | `freight:shipments:write` | Confirmar linhas válidas com `confirm_valid_rows: true`; HTTP 202; estado compatível obrigatório. |
| POST | `/api/v1/freight/order-imports/{batch}/resume` | `freight:shipments:write` | Retomar lote `failed`, `queued`, `parsing` ou `confirming`; sem payload específico além do contexto; HTTP 202. |
| POST | `/api/v1/freight/order-imports/{batch}/dispatch` | `freight:shipments:write` | Solicitar despacho com UUID `connection_id` e `confirm_dispatch: true`; conexão empresarial pronta e lote integralmente importado; HTTP 202. |
| GET | `/api/v1/freight/order-imports/{batch}/rows/{row}/tracking` | `freight:shipments:read` | Snapshot de rastreio/etiquetas de linha aceita; não chama o provedor; HTTP 200. |
| POST | `/api/v1/freight/order-imports/{batch}/rows/{row}/tracking` | `freight:shipments:read` | Solicitar atualização assíncrona Elite; sem payload específico além do contexto; HTTP 202 com `status: queued`; janela de 60 s por lote/linha. |

`freight:financial:read` não fornece um endpoint financeiro nem autoriza pagamento isoladamente. Não existem neste grupo rotas REST JSON para criar pedido avulso, comprar frete novo, baixar etiqueta por rota própria, cancelar envio ou cadastrar webhook. Não use APIs da Postagem/TMS como fallback de Frete.

## Cotação simples: campos e unidades

| Campo | Obrigatoriedade | Formato e limites verificados |
|---|---|---|
| `request_key` | Obrigatório | UUID estável para idempotência da cotação dentro da organização. |
| `freight_company_id` | Condicional | UUID de empresa ativa autorizada; vínculo da chave prevalece; necessário para seleção inequívoca. |
| `freight_location_id` | Condicional | UUID de unidade ativa autorizada da empresa; vínculo da chave prevalece; necessário conforme acesso/origem. |
| `origin_postal_code` | Condicional | String com 8 dígitos; pode vir do cadastro da unidade; precisa estar resolvido antes do cálculo. |
| `destination_postal_code` | Obrigatório | String com 8 dígitos, preservando zeros iniciais. |
| `weight_kg` | Obrigatório | Envie string decimal em kg, ponto decimal, 1–5 dígitos inteiros, até 3 casas; maior que zero e até 50.000 kg. |
| `declared_value_cents` | Obrigatório | Inteiro de 0 a 100.000.000 centavos; valor da mercadoria, não preço do frete. |
| `length_cm`, `width_cm`, `height_cm` | Condicional | Inteiros de 1 a 300 cm. Informar uma dimensão exige as três e `volume_count`. Sem dimensões, é estimativa `weight_only`, não contratável. |
| `volume_count` | Condicional | Inteiro de 1 a 1.000; obrigatório com dimensões. Dimensões agregadas representam volumes iguais. |
| `volumes` | Opcional | Array de 1–1.000 objetos; cada objeto aceita somente `weight_grams`, `length_cm`, `width_cm`, `height_cm`, todos obrigatórios. Peso inteiro de 1–50.000.000 g e dimensões inteiras de 1–300 cm. |
| `service` | Opcional/nulo | String de até 80 caracteres; filtro de serviço conforme tabela. |
| `modal` | Opcional/nulo | `rodoviario`, `aereo`, `maritimo` ou `ferroviario`. |
| `distance_meters` | Opcional | Inteiro de 1–10.000.000 metros, conforme regra tarifária. |
| `invoice_count` | Opcional, cotação simples | Inteiro de 0–1.000; não é aceito nas linhas de `/quotes/bulk`. |

Com `volumes`, a soma dos pesos em gramas deve ser exatamente `weight_kg × 1000` e o tamanho do array deve corresponder a `volume_count` (na ausência deste, a conferência usa 1). Envie `volume_count` explicitamente. O limite de 50.000 kg continua valendo para o total. Para um checkout com cubagem, envie também o conjunto completo de dimensões agregadas; não trate a lista individual como dispensa das condições de `weight_only` do contrato atual.

A cotação simples normaliza CEPs removendo caracteres não numéricos e troca vírgula por ponto no peso. Envie o formato canônico acima: essa normalização não é aplicada individualmente às linhas do lote. Valores monetários devem permanecer inteiros em centavos no cálculo/armazenamento da loja.

### JSON e curl da criação

Os UUIDs abaixo são sintéticos. Substitua o ID da empresa pelo cadastro autorizado; gere seu próprio `request_key`. O exemplo usa empresa sem unidades e origem explícita. Em empresa com unidade vinculada, acrescente `freight_location_id` correspondente.

```json
{
  "request_key": "00000000-0000-4000-8000-000000000001",
  "freight_company_id": "00000000-0000-4000-8000-000000000002",
  "origin_postal_code": "01001000",
  "destination_postal_code": "20040002",
  "weight_kg": "1.000",
  "length_cm": 20,
  "width_cm": 15,
  "height_cm": 10,
  "volume_count": 1,
  "declared_value_cents": 10000
}
```

No terminal de desenvolvimento do **backend**, com `BASE_URL` e `FREIGHT_API_KEY` já definidos pelo mecanismo seguro do seu ambiente:

```bash
curl --request POST "$BASE_URL/api/v1/freight/quotes" \
  --header "Authorization: Bearer $FREIGHT_API_KEY" \
  --header 'Accept: application/json' \
  --header 'Content-Type: application/json' \
  --data-binary @- <<'JSON'
{
  "request_key": "00000000-0000-4000-8000-000000000001",
  "freight_company_id": "00000000-0000-4000-8000-000000000002",
  "origin_postal_code": "01001000",
  "destination_postal_code": "20040002",
  "weight_kg": "1.000",
  "length_cm": 20,
  "width_cm": 15,
  "height_cm": 10,
  "volume_count": 1,
  "declared_value_cents": 10000
}
JSON
```

R$ 100,00 é o valor da mercadoria neste exemplo. O preço do frete vem da resposta. Não execute com trace/verbose que exponha a chave.

### Resposta completa sem ofertas e consulta

Exemplo sintético de HTTP 200 quando não há oferta elegível. `criteria` contém critérios persistidos/normalizados e não inclui `request_key`; empresa/unidade resolvidas e outros campos podem aparecer conforme a entrada. Sem ofertas e com bloqueio fiscal específico, o status pode ser `fiscal_review` em vez de `unavailable`.

```json
{
  "data": {
    "id": "00000000-0000-4000-8000-000000000003",
    "status": "unavailable",
    "criteria": {
      "freight_company_id": "00000000-0000-4000-8000-000000000002",
      "freight_location_id": null,
      "origin_postal_code": "01001000",
      "destination_postal_code": "20040002",
      "weight_kg": "1.000",
      "length_cm": 20,
      "width_cm": 15,
      "height_cm": 10,
      "volume_count": 1,
      "declared_value_cents": 10000
    },
    "options": [],
    "selection": null,
    "shipment_code": null,
    "created_at": "2026-10-08T12:00:00+00:00"
  }
}
```

Guarde `data.id` como `QUOTE_ID`. GET não recebe corpo JSON e retorna o mesmo envelope `data` da criação, com o estado atual, incluindo eventual seleção/contratação histórica posterior:

```bash
curl --get "$BASE_URL/api/v1/freight/quotes/$QUOTE_ID" \
  --header "Authorization: Bearer $FREIGHT_API_KEY" \
  --header 'Accept: application/json' \
  --data-urlencode 'freight_company_id=00000000-0000-4000-8000-000000000002'
```

Acrescente `--data-urlencode 'freight_location_id=UUID_AUTORIZADO'` se a chave/contexto requerer unidade. `QUOTE_ID` é o UUID retornado, não `request_key` nem ID de pedido da loja.

### Como exibir uma oferta no checkout

Com ofertas calculadas, a criação retorna `status: quoted` e `options` contém os snapshots persistidos. A API não devolve a lista visual de comparações do portal: `options` vem diretamente de `offer_snapshots`, sem incorporar ofertas de comparação externa.

| Campo da resposta | Uso na loja |
|---|---|
| `data.id` | ID da cotação consultável em `/quotes/{quote_request}`. |
| `data.options[i].price_cents` | Preço inteiro do frete; por exemplo 2590 → R$ 25,90. Formate apenas para apresentação. |
| `data.options[i].deadline_days` | Prazo em dias calculado pela tabela; não converta automaticamente em data nem prometa dias úteis/calendário sem condição comercial confirmada. |
| `carrier_name` | Nome da transportadora para exibição. |
| `private_carrier_id`, `rate_table_id`, `matrix_version` | Identificadores/versionamento da oferta interna. Não existe `options[i].id` genérico. Guarde também o índice/snapshot escolhido no pedido da loja. |
| `freight_company_id`, `freight_location_id` | Contexto da oferta. |
| `manual_only`, `price_source`, `carrier_workspace_id` | Oferta nova interna: `true`, `private_table` e `null`, respectivamente. Não transformar `private_carrier_id` em `carrier_workspace_id`. |
| `demonstration_only`, `assumptions` | Indicadores/hipóteses de demonstração; não homologam cobrança. |
| `charged_weight_grams`, `cubage` | Peso tarifado e snapshot de cubagem; diferem do peso real conforme a tabela. |
| `price_components`, `calculation_snapshot`, `calculated_at` | Composição e evidência do cálculo. Preserve o snapshot; não recalcule o frete no navegador. |
| `agreement_id`, `subscription_id`, `benefit_id` | Campos do snapshot, nulos nas novas ofertas internas. |
| `data.selection` | Nulo na cotação nova manual; quando histórico selecionado: `price_snapshot_id`, `carrier_workspace_id`, `rate_table_id`, `price_cents`. |
| `data.shipment_code` | Código de envio histórico, se houver; não é o UUID usado na rota `/shipments/{shipment}`. |
| `data.created_at` | Data/hora ISO 8601 ou nulo conforme serializer. |

Uma tabela pode produzir mais de uma opção por serviço. Não considere apenas `rate_table_id` uma identidade universal da opção. Não suponha ordenação nem escolha sempre a primeira. `options: []` significa que não há oferta utilizável naquele resultado: mostre indisponibilidade ou revisão fiscal, sem preço zero, transportadora inventada ou fallback para catálogo operacional/Packslog. A resposta pública da cotação não inclui o diagnóstico interno completo de elegibilidade/falhas.

## Fluxo recomendado do checkout e idempotência

1. O backend da loja valida carrinho e destino, usa o catálogo próprio para obter peso/dimensões/valor e fixa a empresa/unidade autorizadas pelo servidor. Não aceite esses valores comerciais/contextuais como autoridade do navegador.
2. Gere UUID de `request_key` por conjunto de critérios e mantenha-o com a tentativa de cotação. Em falha de comunicação, repita com a mesma chave e os mesmos critérios normalizados. A organização inteira compartilha esse namespace; não reutilize a chave em outro pedido ou empresa.
3. Armazene `data.id`, critérios e snapshots retornados. Idêntico replay devolve a cotação persistida, não recalcula a tabela atual. Mesma chave com critérios diferentes retorna `422` em `errors.request_key`: `Esta chave já foi usada com outra cotação.` Mudança de carrinho, origem, destino ou necessidade de recálculo exige nova chave.
4. O navegador recebe preço/prazo/nome e uma referência da loja para cada opção. Ao confirmar o pedido da loja, o backend confere a referência contra o snapshot guardado e vincula pedido, cotação e opção. Não confie em preço ou ID de transportadora reenviado pelo navegador.
5. Trate `manual_only` como condição comercial explícita: o teste pode registrar a escolha na loja, mas a expedição precisa do fluxo autorizado separado. Cotação e escolha local não confirmam contratação Packsenvios, pagamento, disponibilidade futura da tabela ou despacho.

Para lote de cotações, envie `{"rows":[...]}` com os mesmos critérios em cada linha, UUIDs `request_key` distintos e `external_reference` opcional/nulo de até 80 caracteres. Não envie `invoice_count` nas linhas. Todas as linhas precisam estar no contexto autorizado, inclusive sob vínculo fixo da chave. O retorno é `items`, cada item com `row` (1–20), `externalReference`, `quoteRequestId`, `status` e `optionCount`; consulte os IDs para obter preços/opções. Validação/conflito aborta a transação inteira, sem lote parcialmente gravado. Esse lote é de **cotações**, não um `{batch}` de importação de envios.

## Seleção e contratação históricas

São rotas preservadas, sujeitas à elegibilidade atual; sua existência não garante que haja alguma oferta histórica contratável no ambiente. Seleção recebe JSON com UUIDs `carrier_workspace_id` e `rate_table_id`. Oferta precisa pertencer à cotação, ser elegível e ter preço/prazo/tabela compatíveis. Uma seleção existente pode ser reapresentada com o mesmo par; outro par é recusado. Estimativas `weight_only` e novas ofertas manuais não podem seguir esse fluxo.

A seleção retorna `data.status: selected`, `price_snapshot_id`, `carrier_workspace_id` e `price_cents`. Contratação revalida seleção, expiração, autorização da transportadora, tabela/preço/prazo, conexão e condições fiscais; não é endpoint de pedido JSON avulso. O corpo é multipart para permitir XML fiscal. Campos de checkout verificados:

| Campos | Requisitos principais da contratação histórica |
|---|---|
| `submission_intent`, `fulfillment_method`, `review_confirmed` | `checkout`, `carrier_pickup` e confirmação aceita (`true`). `pickup_window` obrigatório, até 80 caracteres. `pickup_point_workspace_id` proibido. |
| `sender_context` | Opcional: `profile`, `company`, `other`; documentação/empresa do remetente e elegibilidade são revalidadas. CPF/CNPJ não concede autorização. |
| `sender_name`, `recipient_name` | Strings obrigatórias de 2–160 caracteres; DC-e restringe a 2–60. |
| `sender_document`, `sender_email`, `sender_phone` | Documento brasileiro válido e autorizado conforme contexto, email até 160, telefone 10–11 dígitos; obrigatórios. |
| `recipient_document`, `recipient_email`, `recipient_phone` | Documento válido opcional na regra geral, obrigatório para DC-e; email opcional até 160 (60 na DC-e); telefone obrigatório 10–11 dígitos. |
| `origin_*`, `destination_*` | CEP 8 dígitos; destino diferente da origem. `street` 2–255, `number` até 32, `district`/`city` 2–120, `state` 2 caracteres, `country: BR`, obrigatórios. `complement` até 120 e `reference` até 160, opcionais/nulos. DC-e restringe rua/bairro/cidade a 2–60, complemento a 60 e UF à lista brasileira. |
| `package_weight_grams`, `package_length_cm`, `package_width_cm`, `package_height_cm`, `package_volume_count` | Obrigatórios; peso inteiro 1–50.000.000 g, cada dimensão 1–300 cm, volumes 1–1.000. Devem corresponder ao cotado. |
| `package_preset`, `cargo_description`, `declared_value_cents` | Preset obrigatório até 80; descrição obrigatória 3–1.000; valor inteiro positivo em centavos. A regra de Frete substitui o teto de valor do request herdado; gates comerciais/fiscais continuam aplicáveis. |
| `fiscal_document_type`, `nfe_xml`, `dce_xml` | Checkout atual aceita `nfe` ou `dce`, com validações fiscais próprias. XML quando enviado: tipo XML, até 2.048 KiB. Não envie `nfe_access_key` manual: proibido. Ausência de XML pronto não comprova autorização fiscal/conclusão. |
| `dce_operation_nature`, `dce_non_contributor_confirmed`, `dce_no_fiscal_document_confirmed` | Na DC-e: natureza `gift`, `return`, `personal_effects`, `transfer` ou `other` e duas confirmações aceitas. Empresa/inscrição estadual e suporte de integração podem bloquear. |
| `expected_price_cents`, `expected_deadline_days` | Excluídos pelo request de Frete; prevalece snapshot persistido no servidor. |

Esse quadro delimita o fluxo legado, não o recomenda para automatizar ofertas novas nem certifica documentos fiscais. O resultado contém `data.status` (`contracted` ou `fiscal_review`), `shipment_id`, `shipment_code`, `carrier_workspace_id`, `quote_id`, `price_cents`, `payment_id`, `payment_status`; campos comerciais podem ser nulos em revisão fiscal. `quote_id` desse resultado não substitui o `data.id` da requisição de cotação. Replay já contratado recupera resultado persistido. Após resposta incerta, consulte a cotação/estado antes de repetir qualquer operação com efeito financeiro.

## Importação CSV/XLSX e despacho separado

Este é o caminho Bearer existente para importar pedidos: não há `POST /orders` JSON. Use o modelo do portal **Meus Envios → Importação**, disponível por sessão autorizada em `/gestao-frete/{workspace_slug}/envios/importacoes/modelo`. `{workspace_slug}` é o slug real do portal, não UUID da empresa. O modelo atual tem 28 colunas, instrução na primeira linha, cabeçalho na segunda e dados a partir da terceira. Preserve grafia e ordem do modelo. Modelos anteriores de 27 e 30 colunas também são aceitos com regras próprias; prefira o atual.

As 28 colunas atuais correspondem, em ordem, a: número da nota, chave NF-e, nome/documento/telefone do destinatário, CEP/rua/número/complemento/bairro/cidade/UF do destinatário, quantidade de volumes, quantidade de itens, valor total, peso em kg, nome/documento do remetente, CEP/rua/número/complemento/bairro/cidade/UF do remetente, altura/largura/comprimento em cm. O modelo de 30 inclui cubagens informada/medida antes do remetente; o atual calcula cubagem pelas dimensões. Não é uma planilha apenas de CEP/peso.

Limites e validações do modelo atual:

- Arquivo multipart com campo `file`, extensão CSV/XLSX e MIME compatível; máximo HTTP de **29.296 KiB**. O leitor também limita a 30.000.000 bytes; respeite ambos. XLSX usa a primeira worksheet, aceita até 500 entradas ZIP e limita conteúdo descompactado a 300.000.000 bytes, com controles adicionais de textos/nós XML.
- Até **200.000 envios** por arquivo; CSV tem limite estrutural de 1.048.576 linhas e 64 células por linha. CSV aceita `;` ou `,`, detectados pelo cabeçalho, UTF-8 ou Windows-1252. Preserve zeros à esquerda e chave NF-e como texto.
- Campos preenchidos com até 180 caracteres e sem controles inválidos. No upload atual, complementos também são cobrados pelo validador; a flexibilização do editor assistido não é regra do upload.
- CPF/CNPJ com dígitos verificadores válidos; CEP com 8 dígitos; UF brasileira; NF-e com chave válida de 44 dígitos. Telefone destinatário com DDD, padrão de 8–22 caracteres com dígitos/espaços/parênteses/hífen e `+` inicial opcional.
- Número da nota 1–999.999.999, volumes 1–1.000, itens 1–1.000.000; dimensões inteiras 1–300 cm. Peso positivo em kg com até 3 casas (até 6 dígitos inteiros na validação da planilha; isso não amplia limites de cotação/preparação posteriores).
- `Valor Total` é **reais** com até 7 dígitos inteiros e duas casas, convertido internamente a centavos; não é o inteiro em centavos do JSON de cotação. Sem notação científica; limites de preparação/cotação ainda se aplicam. Nas versões com cubagens, valores positivos em m³ até 6 casas, conforme o modelo; no modelo com dimensões são calculadas quando omitidas.
- Capacidade por organização/titular: no máximo 10 arquivos pendentes armazenados e 3 lotes em `queued`, `parsing` ou `confirming`; exceder retorna `429`.

Envie `freight_company_id` obrigatório e `freight_location_id` quando aplicável. Exemplo de upload no backend, apontando `ORDERS_FILE` para arquivo sintético já preenchido conforme o modelo:

```bash
curl --request POST "$BASE_URL/api/v1/freight/order-imports" \
  --header "Authorization: Bearer $FREIGHT_API_KEY" \
  --header 'Accept: application/json' \
  --form "file=@$ORDERS_FILE" \
  --form 'freight_company_id=00000000-0000-4000-8000-000000000002'
```

Somente o titular criador pode consultar/operar o lote, mesmo com outra chave de Frete autorizada. O upload deduplica por conteúdo do arquivo, organização, titular, empresa e unidade; não usa `request_key` de cotação. O mesmo conjunto reutiliza o lote. HTTP 202 retorna resumo com `id`, `filename`, `status`, `total`, `valid`, `invalid`, `imported`, `duplicates`, `processed`, `issue`, `createdAt`, `canDelete`, `tmsAvailable` e `dispatch`. `canDelete` refere-se a ação do portal, não a endpoint DELETE Bearer.

1. Guarde o `id` como `BATCH_ID`. Consulte GET `/order-imports/{batch}` com contexto na query string. `cursor` começa em 0; para filtrar inconsistências use `errors_only=1` (evite a string literal `true`, que não é o formato booleano validado pelo request). O retorno acrescenta `items`, `hasMore` e `nextCursor` no nível raiz; cada item inclui `row`, `status`, `invoiceNumber`, `recipientName`, `destination`, `volumes`, `weightKg`, `errors`, `shipmentId`, `publicCode`, `dispatchStatus`.
2. Espere validação completa. POST `/confirm` recebe JSON `{"confirm_valid_rows":true}`; estados aceitos: `review`, `confirming`, `imported`, com pelo menos uma linha válida. Linhas inválidas não viram envio. Corrija pelo fluxo existente do portal ou envie arquivo corrigido. O gateway não expõe edição de linha por Bearer.
3. Para despacho, espere `imported` com todos os itens importados e nenhuma inconsistência. POST `/dispatch` recebe JSON `{"connection_id":"00000000-0000-4000-8000-000000000004","confirm_dispatch":true}`. Substitua o UUID pela conexão da empresa, configurada, ativa, testada e homologada. Quando há preparação vinculada à cotação, o destino precisa corresponder à transportadora selecionada. A API não descobre/cadastra essa conexão por Bearer.
4. O despacho retorna HTTP 202 com `id`, `batchId`, `connectionId`, `status`, `total`, `enqueued`, `accepted`, `rejected`, `uncertain`, `issue`. Repetição conserva a solicitação existente e não permite mudar conexão. Consulte o lote para acompanhar `dispatch`; enfileiramento não significa aceitação pela transportadora. `dispatch_queue_unavailable` é falha de publicação na fila, não confirmação de envio.
5. POST `/resume` retoma importação em estado permitido; não reconcilia nem reenvia despacho incerto. `uncertain` exige reconciliação no fluxo existente, nunca reenvio cego. Um arquivo corrigido com conteúdo diferente não é protegido pela deduplicação de upload contra toda possível duplicação comercial; confira referências/estado antes de reenviar.

Filas e jobs são necessários para validação, confirmação e despacho. Neste trabalho elas não foram ativadas; a cópia local de produção mantém filas/scheduler suspensos. A implementação local não confirma execução desses passos. A loja de teste deve prever estados pendentes e um ambiente especificamente autorizado/pronto para integração.

## Consulta, rastreamento e IDs distintos

GET `/shipments` retorna `items` e `pagination`; GET `/shipments/{shipment}` retorna `shipment`, `events`, `pagination`. Paginação até 20 itens/eventos, `pagination.hasMore`, `nextCursor`, `perPage: 20`. Reenvie cursor opaco intacto e codificado na URL; não é número de página. A API Bearer valida apenas `cursor` como filtro específico dessa listagem; filtros adicionais usados no portal não devem ser presumidos disponíveis na API.

O resumo histórico usa `id`, `code`, `carrierName`, `originPostalCode`, `destinationPostalCode`, `status`, `priceCents`, `deadlineDays`, `volumeCount`, `createdAt` e, no serializer atual, também `recipientName`, `destinationLabel`, `trackingCode`. Preço/prazo podem ser nulos. Eventos usam `id`, `status`, `title`, `description`, `occurredAt`; não retornam payload bruto do TMS ou evidência fiscal.

Para **pedidos importados**, consulte `/order-imports/{batch}/rows/{row}/tracking` usando `items[].row`, que é linha da planilha (normalmente começa em 3), não posição zero do array. Só linhas aceitas pela transportadora possuem esse rastreamento. GET retorna `code`, `reference`, `acceptedAt`, `updatedAt`, `issue`, `labels`, `labelsAt`, `events`; `labels` e eventos podem estar vazios. As etiquetas são projeções normalizadas por volume, não uma promessa de rota de compra/download. GET lê o snapshot, com `Cache-Control: private, no-store`. POST no mesmo caminho retorna `{"status":"queued"}` e HTTP 202, solicitando atualização Elite; deduplicação de 60 segundos é compartilhada com o portal, e quotas do provedor continuam valendo. Não significa que o rastreio já foi atualizado.

| Identificador | Onde usar |
|---|---|
| `request_key` | Replay de criação de cotação; não é ID de recurso consultável. |
| `data.id` da cotação / `quoteRequestId` de bulk | `/quotes/{quote_request}`. |
| `shipment_id` histórico / `id` de `/shipments` | `/shipments/{shipment}`; UUID de envio histórico. |
| `shipment_code` / `code` histórico | Código público; não substitui o UUID no caminho. |
| `id` do upload (`BATCH_ID`) | `/order-imports/{batch}`. |
| `items[].row` | `/order-imports/{batch}/rows/{row}/tracking`. |
| `items[].shipmentId` do lote / `data.shipmentId` de webhook | ID nativo de envio importado; não usar em `/shipments/{shipment}`. Mantenha a associação lote/linha na loja. |
| `id` da solicitação de despacho | Acompanhamento em `dispatch` do lote; não é `BATCH_ID`. |

## Webhooks: evidência local, não homologação

Há implementação de webhooks próprios de Frete em **alterações locais preexistentes**, incluindo arquivos ainda não versionados. Este guia confirma a leitura desses contratos, não migrations executadas, worker disponível, entrega testada ou homologação externa. O marcador `active` da documentação gerada não comprova disponibilidade operacional. As entregas dependem das tabelas/configuração/filas do ambiente; nenhuma fila foi ativada para este trabalho.

O cadastro é pela aba **Webhooks** de Integrações do portal, com sessão autenticada, contexto empresarial/unidades e `freight.integrations.read/manage`. As rotas de portal ficam em `/gestao-frete/{workspace_slug}/integracoes/webhooks...`; não são endpoints Bearer. Use destino HTTPS público, porta 443, sujeito às validações de destino público do backend; localhost/endereço privado da loja não é destino homologado. O segredo de assinatura é independente da chave API, exibido ao criar/substituir e guardado somente no servidor receptor.

Eventos confirmados no código: `shipment.created`, `shipment.dispatch_updated`, `shipment.tracking_updated`, `shipment.labels_updated`; teste explícito usa `webhook.test`, sem envio real. O corpo mínimo contém `version: 1`, `id`, `type`, `occurredAt`, `companyId`, `locationId` e `data` com `shipmentId`, `publicCode`, `dispatchStatus`. Atualização de rastreio/etiquetas sinaliza mudança; recupere detalhes pela consulta autorizada do lote/linha. O evento não entrega o arquivo de etiqueta nem o pedido completo.

Validação no receptor, antes de processar:

1. Capture o **corpo HTTP exato**, antes de decodificar/reformatar JSON.
2. Leia `X-Packsenvios-Timestamp` e `X-Packsenvios-Signature`. A assinatura é `v1=` seguido de HMAC-SHA256 hexadecimal de `timestamp + '.' + corpo_exato`, com o segredo da assinatura. Compare em tempo constante.
3. A loja deve rejeitar timestamp inválido ou fora de janela de cinco minutos e assinatura inválida. Essa janela é controle recomendado ao receptor; não é garantia de validação de entrada pela Packsenvios.
4. Deduplique `id`; `X-Packsenvios-Delivery` contém o mesmo ID do evento em retries/reenvios. Eventos podem repetir/chegar fora de ordem. Confirme com HTTP 2xx após recebimento seguro; consulte estado atual quando necessário.

O código prevê até oito tentativas por ciclo, timeouts de conexão/resposta de 3/8 segundos e limites configurados de 60 entregas/minuto por host e 300 por empresa, até 20 subscriptions por empresa. Não confundir esses limites de saída com a quota Bearer. Pausa/exclusão, perda de autoridade ou mudança de configuração bloqueiam novas entregas; destino/abrangência alterados exigem revisão e reenvio explícito pelo portal. Histórico, teste e reenvio são operações do portal. Não derive disponibilidade desses limites sem validar o ambiente.

## Erros, limites e retentativas

| HTTP | Situação e ação da loja |
|---|---|
| 200 | Cotação/consulta ou resultado histórico; verificar `status` e `options`, não apenas HTTP. |
| 202 | Solicitação assíncrona aceita/enfileirada; acompanhar estado, sem declarar conclusão. |
| 401 | Sem autenticação válida; verificar chave/expiração/revogação. |
| 403 | Chave de domínio incorreto, ability/grant ausente, titular/contexto sem autoridade ou usuário não verificado; não tentar outro tenant. |
| 404 | ID/rota inválido ou recurso fora do contexto acessível; lote de outro titular/linha sem aceitação também pode não estar disponível. |
| 409 | Estado incompatível de lote/despacho/conexão ou conflito de persistência; consultar estado e corrigir a condição antes de repetir. |
| 422 | Campos inválidos, seleção contextual ausente, replay divergente ou bloqueio comercial/fiscal; apresentar mensagem apropriada e corrigir os critérios. |
| 429 | Quota de chamadas ou capacidade de importação; respeitar `Retry-After` quando houver. Capacidade de lotes/arquivos pode exigir conclusão/gestão pelo portal, não apenas espera. |
| 503 | Falha de storage/enfileiramento em caminhos que a reportam; consultar persistência antes de repetir. Falha de rede/5xx não prova que não houve efeito. |

Erros de validação Laravel retornam `message` e `errors` por campo com `Accept: application/json`; não presuma uma mensagem fixa para todos os erros. Exemplo real de estrutura para conflito de idempotência:

```json
{
  "message": "Esta chave já foi usada com outra cotação.",
  "errors": {
    "request_key": ["Esta chave já foi usada com outra cotação."]
  }
}
```

O limitador geral tem padrão configurado de **120 requisições/minuto**, ajustável pelo ambiente, agregado pela organização Frete. Trocar/criar chaves não multiplica essa quota. O limitador geral retorna `message: Muitas requisicoes. Tente novamente em instantes.` e `error: rate_limited` em 429. `/quotes/bulk` tem ainda **3 requisições/minuto por organização**, com resposta do throttle correspondente. Use espera progressiva e preserve idempotência após timeout/429; não faça retry infinito de 401/403/422 nem redespacho cego após resposta incerta. Não foi consultada configuração efetiva do ambiente nem executada chamada para medir disponibilidade/quota.

## OpenAPI no portal e diferenças verificadas

A página autenticada é `/gestao-frete/{workspace_slug}/integracoes/documentacao`; o JSON é `/gestao-frete/{workspace_slug}/integracoes/documentacao/openapi.json`, com sessão e autoridade de Integrações. Não é endpoint Bearer público. A especificação filtrada contém as rotas `/api/v1/freight/...`, e seu servidor relativo `/` significa o ambiente atual, não um domínio de produção.

O contrato local tem diferenças que o integrador precisa conhecer:

- O request aceita `volumes` e verifica soma de pesos/quantidade, mas o schema OpenAPI de cotação não lista esse campo. Não rejeite a funcionalidade apenas por geração de cliente a partir desse schema.
- O OpenAPI lista `invoice_count` na cotação simples; o request de bulk não o aceita nas linhas.
- O exemplo gerado do portal combina `status: quoted` com `options: []`. Na criação atual, sem snapshots o status é `unavailable` ou `fiscal_review`; este guia usa o comportamento da Action.
- O schema histórico de contratação herda limites/formas de Postagem que não refletem todas as substituições do request de Frete e a evolução fiscal: por exemplo, peso/dimensões/volumes maiores, `review_confirmed` obrigatório e DC-e no checkout. Não use o schema herdado para concluir suporte a declaração de conteúdo nesse checkout.
- O serializer histórico de envios inclui `recipientName`, `destinationLabel`, `trackingCode`, além dos campos descritos no schema. O guia não depende de `additionalProperties: false` para descartá-los.

Essas diferenças foram documentadas sem alterar a API, o OpenAPI ou o guia existente. Para a loja de teste, o recorte necessário é cotação simples + consulta + tratamento de ofertas manuais/vazias; curl e JSON bastam para especificar a chamada, sem introduzir framework ou dependência de servidor.

## Checklist de teste da loja

- Confirmar URL/alcance do ambiente com o responsável, empresa ativa, chave de Frete e acesso atual do titular; usar exclusivamente dados e cadastros sintéticos de ambiente autorizado.
- Confirmar transportadoras vinculadas, tabela **atual** ativa, vigência, cobertura, peso, serviço/modal e gates fiscais. Preparar casos com oferta, sem cobertura e revisão fiscal quando disponíveis.
- Cotar e consultar o mesmo `data.id`; conferir preço em centavos, prazo em dias, contexto e `manual_only`; não marcar pedido como contratado pela rede.
- Repetir mesma chave/critérios e conferir mesmo ID; trocar critérios com a mesma chave e esperar 422; gerar nova chave para recálculo.
- Testar CEP/peso/dimensões/valor inválidos, dimensão incompleta, limites excedidos e volumes cuja soma/quantidade divergem. Testar peso sem dimensões como estimativa.
- Testar ausência de credencial, chave revogada/expirada, chave Postagem, ability ausente, usuário/grant revogado, outra empresa/unidade e ID de outra organização/titular. Esperar recusa, sem dados vazados; distinguir 401/403/404/422 conforme o caso.
- Conferir que o navegador nunca recebe Bearer nem permite mudar preço/empresa pelo body; ocultar chave e dados sensíveis nos logs de erro/monitoramento da loja.
- Simular timeout/429 e retentativa controlada, sem repetir efeitos financeiros/despachos. Testar `options: []` sem preço zero/fallback; tratar `demonstration_only` como demonstração.
- Se testar importação em ambiente autorizado, usar modelo sintético, tamanho/linhas válidos, repetir arquivo, acompanhar validação/confirmar, verificar IDs lote/linha e recusar despacho incompleto/destino diferente. Não usar dados fiscais de terceiros.
- Se testar webhooks após disponibilização/homologação específica, validar HMAC no corpo exato, timestamp vencido, assinatura inválida, repetição e ordem invertida; manter associação envio nativo → lote/linha e não ativar filas compartilhadas por iniciativa própria.
- Registrar separadamente testes locais da loja, testes HTTP da API, processamento assíncrono e entrega externa. Implementar checkout local não comprova deploy ou execução externa de nenhum desses componentes.

## Evidência e validação deste documento

Finalidade: orientar ecommerce de teste para cotar na loja e reconhecer os limites comerciais/operacionais reais. Impacto/contrato: documentação standalone do checkout inspecionado; nenhuma implementação de app/API, mudança de contrato ou promessa de implantação. Decisão: reutilizar rotas/requests/serializers existentes, com exemplos JSON/curl, sem código de servidor ou dependências adicionais.

Fontes locais inspecionadas: `routes/api.php`, `routes/freight_management.php`, `FreightApiController`, `AuthorizeFreightApiCredential`, `FreightApiAbilities`, requests de cotação/seleção/contratação (incluindo o request herdado), `FreightQuoteCriteriaRules`, `ResolveCompanyFreightOptionsQuery`, Actions de criação/bulk/seleção/contratação, serializers de cotação/envios, `ManageFreightShipmentImportAction`, `FreightShipmentImportTemplate`, `FreightClientWorkbookReader`, `ManageFreightDispatchAction`, limitadores/`ApiRateLimitKey`, `BuildFreightApiDocumentationQuery`, `docs/contracts/openapi/v1.json` e `docs/domains/freight-api-integration-guide.md`. Webhooks: Actions de configuração/enfileiramento/entrega, job e configuração locais preexistentes. Esses nomes registram evidência; a integração descrita acima não exige acesso aos documentos internos.

Validação: revisão manual de métodos/permissões, campos/unidades, envelopes e limitações contra código/OpenAPI; conferência sintática dos JSONs/exemplos e diff. Sem chamadas à API, execução de testes de aplicação, build, Docker, migrations, ativação de filas ou validação de deploy. Diferenças de schema estão explicitadas acima. Não há links externos a verificar.

Dados pessoais: nao aplicavel — somente documentação e exemplos sintéticos, sem dados reais/credenciais. Gate LGPD: GO para este delta documental; não decide base legal, finalidade ou retenção da futura operação da loja.
