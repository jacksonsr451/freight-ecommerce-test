# Decisões e riscos — freight-ecommerce-test (Prompt 00)

Registro histórico de decisões (ADR curto) e riscos da preparação inicial. Contrato de referência: `docs/reference/gestao-frete-integracao-ecommerce-teste.md`; matriz em `docs/architecture/contract-matrix.md`; plano em `docs/architecture/execution-plan.md`. A decisão provisória de adoção do framework de testes foi concluída no prompt 19 com jsr-testrunner.

**Estado de revisão:** propostas para revisão pelo usuário. A expressão “aceita” nos registros abaixo indica adoção nesta proposta técnica, não aprovação já concedida pelo usuário. Restrições expressas no prompt (Bearer exclusivo no backend, compra local e bloqueio de contratação automática de `manual_only`) são requisitos obrigatórios.

## D1 — Fonte única de contrato

- **Decisão:** o documento de referência é a única fonte contratual da integração Packsenvios. Nenhum endpoint, payload, campo, status ou permissão será inferido de outras fontes.
- **Contexto:** o snapshot local `packslogenvios` (commit `f9c8906b`) está em base **divergente** da base documentada (`0e860f0…`, ausente no repositório) e tem a árvore de trabalho suja (~422 deleções, incluindo todos os `routes/*.php`). Ele não contém as rotas `/order-imports/*`.
- **Consequências:** tipos e fixtures derivam da documentação; divergências OpenAPI (O1–O8) ficam registradas na matriz; o código local é somente leitura e apenas corroborativo (rotas 1–7 conferidas via `git show HEAD:routes/api.php`).
- **Status:** aceita.

## D2 — Mock por padrão, real opcional e condicionado

- **Decisão:** `FREIGHT_MODE=mock|real` (default `mock`); `FREIGHT_BASE_URL` e `FREIGHT_API_KEY` existem somente no backend. Modo real exige ambiente autorizado, credencial emitida no portal e checklist da seção 8 da matriz.
- **Consequências:** a jornada local deverá funcionar sem rede externa; testes HTTP reais ficam `SKIP` com motivo explícito enquanto disponibilidade e autorização não forem confirmadas. Fixtures de resposta Packsenvios serão **sintéticas, marcadas como tais** e rastreáveis por TODO. Nenhuma funcionalidade dessa jornada foi implementada nesta etapa.
- **Status:** aceita.

## D3 — Bearer exclusivamente no backend

- **Decisão:** o navegador nunca recebe a chave, nem a vê em URL, storage, logs, analytics ou erros. O frontend consome apenas a API local da loja; seleção de opção envia **referência interna da loja**, nunca preço/ID externo arbitrário (doc L187).
- **Status:** aceita (imutável; critério de aceite de todos os prompts).

## D4 — Compra/pagamento/pedido são locais e simulados

- **Decisão:** pagamento e pedido são simulações da loja com registro explícito `simulation=true`; nada alega pagamento real ou contratação Packsenvios. No checkout, cotação e consulta podem usar a API real. Importação, despacho e rastreamento reais constituem um fluxo operacional separado, opcional, condicionado aos pré-requisitos dos prompts 13–14 e à confirmação explícita do operador. Webhooks externos dependem de disponibilização e validação próprias (15/18).
- **Status:** aceita.

## D5 — `manual_only` nunca é contratado automaticamente

- **Decisão:** ofertas com `manual_only: true` exibem preço/prazo no checkout, podem registrar escolha local vinculada ao snapshot, mas **nunca** disparam seleção/contratação automática (as rotas 4/5 da matriz as recusam, doc L194). Expedição segue fluxo autorizado separado (importação/despacho) com confirmação humana.
- **Consequências:** o checkout não chama `/selection` nem `/contract` (fora do recorte da loja, doc L325); opções `weight_only` também não são contratáveis.
- **Status:** aceita.

## D6 — Importação é assíncrona, titular e com confirmação explícita

- **Decisão:** o fluxo de importação modela estados `202` + polling (`queued`/`parsing`/`review`/`confirming`/`imported`/falhas), dedupe de upload, quotas (10 arquivos/3 lotes) e titularidade. `confirm` e `dispatch` exigem ação explícita do operador após validação; `resume` não reconcilia `uncertain`; `uncertain` nunca tem reenvio cego (doc L243–L246).
- **Contexto de risco:** filas/jobs **não** estavam ativos no ambiente inspecionado (doc L248) — a loja deve suportar pendência e degradar com clareza.
- **Status:** aceita.

## D7 — Identidades externas preservadas

- **Decisão:** `request_key`, `data.id`, `BATCH_ID`, `items[].row`, `shipmentId` nativo importado, `shipment_id` histórico, `shipment_code` e id da solicitação de despacho são armazenados em colunas distintas, sem fusão (matriz §6).
- **Status:** aceita.

## D8 — Tipos próprios, sem codegen do OpenAPI

- **Decisão:** gerar modelos tipados (Pydantic no backend, TS no frontend) a partir do documento de referência, incluindo campos que o OpenAPI local omite (`volumes`) e campos extras do serializer (`recipientName`, `destinationLabel`, `trackingCode`). Campos opcionais permanecem opcionais; **não** assumir `options[i].id` nem ordenação de `options`.
- **Status:** aceita.

## D9 — Webhook: implementável, não homologado

- **Decisão:** receptor local com captura do corpo **exato**, HMAC `v1=` em tempo constante, janela de 5 min, dedupe por `id` e persistência antes do `2xx` — mas todo resultado é rotulado **não homologado** até teste com entrega externa autorizada (destino HTTPS público 443). Eventos apenas sinalizam mudança; estado real vem da consulta autorizada (doc L283).
- **Status:** aceita.

## D10 — Convenções de dados

- **Decisão:** UUIDs, dinheiro em centavos (inteiros), `weight_kg` como string canônica (ponto decimal, ≤3 casas), timestamps UTC, transições de estado explícitas. A planilha usa `Valor Total` em **reais** convertido internamente a centavos (doc L227) — conversão apenas no backend.
- **Status:** aceita.

## D11 — Política de retentativa

- **Decisão:** retry de comunicação reutiliza `request_key` e critérios idênticos; `Retry-After` respeitado em 429; sem retry de 401/403/422; após resposta incerta em efeito financeiro, consultar estado antes de qualquer repetição; nunca retry infinito nem reenvio cego de `uncertain`.
- **Status:** aceita.

## D12 — Sem homologação assumida

- **Decisão:** nenhum prompt pode afirmar teste real, quota medida, entrega de webhook ou contratação sem evidência de execução em ambiente autorizado. Evidências são separadas em: testes locais da loja / HTTP da API / processamento assíncrono / entrega externa (doc L339).
- **Status:** aceita.

## D13 — Raiz do projeto e layout

- **Decisão proposta:** os artefatos desta auditoria ficam em `E:\Softwares\joao\docs\architecture`, ao lado da fonte contratual. O diretório definitivo do monorepo será definido no prompt 01: a presença da documentação na pasta pai não comprova que ela deva se tornar a raiz Git da loja. O snapshot `packslogenvios/` é um repositório independente e não deve ser incluído no Git da loja. `tests/validate_contract_matrix.py` valida somente esta auditoria.
- **Status:** proposta de layout para revisão no bootstrap; ainda não existe aplicação da loja.

---

## Riscos

| ID | Risco | Impacto | Mitigação |
|---|---|---|---|
| R1 | Snapshot local `packslogenvios` diverge da base documentada (sem rotas `/order-imports/*`; working tree sujo) | Alto | Contrato somente pelo documento (D1); nunca executar código/migrations desse snapshot; marcar rotas 8–14 como não corroboradas por código |
| R2 | Docker Desktop instalado mas **daemon parado** no ambiente | Alto para prompt 02+ | Subir daemon antes do 02; prompt 02 inclui healthcheck; nenhum outro prompt depende de rede externa |
| R3 | `pip` do PATH pertence a venv de terceiro (`hermes-agent`); `py` launcher inexistente | Médio | Usar Poetry 2.4.0 + venv do projeto por serviço; nunca instalar dependências globais |
| R4 | Sem cliente `psql` no host | Baixo | Operar banco apenas via container Docker |
| R5 | Filas/scheduler inativos no ambiente inspecionado; importação/despacho reais exigem ambiente autorizado | Alto para 13/14 | Modelar pendência (D6); testes de fila = SKIP com motivo; prompt 13 em modo real gated |
| R6 | Quotas/rate limits reais não medidas (120/min é default configurável) | Médio | Backoff com `Retry-After`; diagnóstico (prompt 16) expõe latência/erros normalizados |
| R7 | Ambiente autorizado pode não ter tabelas/transportadoras/CEPs elegíveis → `options: []` frequente | Médio | Tratar `unavailable`/`fiscal_review` como estados válidos de UI; nunca fabricar preço |
| R8 | Diretório definitivo da loja não especificado; documentação e prompts estão na pasta pai do diretório de trabalho | Baixo | D13 registra o local da auditoria; definir raiz isolada no prompt 01 sem incluir o repositório independente `packslogenvios` |
| R9 | Nenhuma chamada HTTP foi feita; OpenAPI portal exige sessão | Informativo | Matriz §10 lista lacunas; prompt 17 gera matriz PASS/FAIL/SKIP sem alegar execução |
| R10 | Janela de 5 min de webhook é controle do receptor, não garantia da Packsenvios | Baixo | Documentado no receptor (prompt 15); reconciliação via consulta autorizada |
| R11 | `request_key` compartilha namespace por organização inteira | Médio | Gerar UUIDv4 por tentativa; nunca reutilizar entre pedidos/empresas; persistir com a tentativa |
| R12 | Plano de arquivos importados deduplicados por conteúdo, mas arquivo corrigido pode duplicar comercialmente | Médio | Prompt 13 exige conferência de referências/estado antes de reenvio |

## Pendências rastreáveis (TODO com dono de prompt)

| TODO | Prompt |
|---|---|
| TODO(fixture): criar fixtures sintéticas de `quoted`, `unavailable`, `fiscal_review`, `weight_only`, `manual_only` a partir da matriz §3–§4 | 06/07 |
| TODO(tipo): modelar `volumes[]` ausente no OpenAPI (O1) e campos extras do serializer (O5) | 06/17 |
| TODO(gated): testes HTTP reais e quotas — habilitar somente com ambiente autorizado (`BASE_URL` + chave) | 17/18 |
| TODO(filas): validar `confirm`/`dispatch`/tracking refresh com filas ativas em ambiente autorizado | 13/14 |
| TODO(webhook): homologação externa com destino HTTPS público antes de afirmar recebimento | 15/18 |
| TODO-IMPORT-TEMPLATE: obter grafia literal dos 28 cabeçalhos do modelo oficial antes de certificar exportação compatível | 13 |
| TODO-SCHEMA-DETAIL: confirmar estruturas aninhadas e respostas incompletas no guia sem inventar campos ou grants | 06/13/14/17 |
| TODO(bootstrap): definir raiz definitiva do monorepo e revisar adoção de pytest, condicionada no prompt 01 | 01 |
