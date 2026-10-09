# 03 — Modelo de domínio e persistência

Raiz: `E:\Softwares\joao\tests`. PostgreSQL + SQLAlchemy 2 + psycopg + Alembic.
Os pré-requisitos de conexão/migrations ausentes após o bootstrap foram incluídos nesta etapa.
O healthcheck permanece liveness; nenhuma conexão/migration é executada no startup da API.

## Entidades e invariantes

| Entidade | Persistência / invariantes principais |
|---|---|
| Product | SKU único, preço inteiro não negativo, peso gramas e dimensões válidas; cadastro mutável |
| Inventory | Um registro por produto; `0 <= reserved <= on_hand`; versionamento otimista |
| Customer | UUID local e unicidade de email normalizado por índice `lower(email)` |
| Address | FK do cliente, CEP 8 dígitos preservando zeros; país BR e UF de 2 caracteres |
| Cart | Cliente opcional, revisão comercial positiva; ciclo local e versão otimista |
| CartItem | Par carrinho/produto único; quantidade positiva; único cascade é item de carrinho |
| CheckoutAttempt | Carrinho, revisão, cliente e endereço; FK composta impede endereço de outro cliente |
| FreightQuote | Critérios JSONB e request_key estáveis; namespace local de integração; identidade consultável externa separada |
| FreightOptionSnapshot | UUID **interno**, índice no resultado, preço/prazo, flags e payload JSONB; imutável |
| Order | Chave idempotente própria, um por tentativa, cliente e escolha consistente; totais em centavos e `simulation=true` |
| OrderItem | Produto e preço/peso congelados em snapshot; quantidade positiva e total de linha coerente; imutável |
| PaymentSimulation | Chave idempotente própria, `simulation=true`; FK composta garante valor igual ao total do pedido |
| Fulfillment | Um por pedido, status local; IDs históricos/nativos e associação lote/linha em colunas separadas |
| ShipmentImportBatch | Titular/contexto/hash e chave de dedupe locais; UUID externo de lote separado, contadores não negativos |
| TrackingEvent | Origem `simulated` ou `packsenvios`, evento deduplicado por fulfillment/origem/chave; timestamp UTC |
| IntegrationAudit | Correlação, modo/origem, operação, erro/latência e referências; details devem ser redigidos pelo serviço futuro |

Todas as PKs locais são UUIDs gerados no backend. Dinheiro é `BIGINT` em centavos; nenhum float
é utilizado. Timestamps são `timestamptz`, valores sem timezone são recusados pelo tipo ORM,
e datas lidas pela aplicação são normalizadas a UTC. Conexões criadas pelo projeto usam UTC.
UUIDs são defaults Python; SQL manual deve fornecer PKs explicitamente.

FKs compostas ligam pedido → tentativa/cliente, cotação → tentativa, opção → cotação/preço,
pagamento → pedido/valor. Assim o navegador não pode escolher outro snapshot/preço arbitrário
por meio de um registro persistido coerente. Descontos são campos locais, nunca alterações da oferta.
Validação de soma de todas as linhas do pedido e reserva de estoque será parte dos serviços 05/11;
essa etapa não implementa fechamento de compra ou reserva automática.

## Identidades externas (fonte contratual L31, L148–L190, L258–L267)

- `FreightQuote.request_key`: replay, não ID consultável.
- `FreightQuote.external_quote_request_id`: `data.id`/`quoteRequestId`, UUID consultável.
- `ShipmentImportBatch.external_batch_id`: UUID do lote, diferente da PK interna.
- `Fulfillment.historical_shipment_id`: UUID de `/shipments/{shipment}`.
- `Fulfillment.imported_shipment_id`: ID nativo importado, **não usado** na rota histórica.
- `Fulfillment.import_batch_id` + `import_row_number`: vínculo com PK local de lote e número real da planilha.
- Código público e id da solicitação de despacho também não substituem os IDs acima.

IDs nativos importados e de despacho são armazenados como strings opacas, pois o guia não
especifica integralmente seus tipos. PKs da loja permanecem UUID. Não inferir um identificador
`options[i].id`: a referência da opção é o UUID local + índice/snapshot.
`integration_scope` é um namespace **local** da organização configurada, não campo de request
nem seletor de tenant da API. Chaves são únicas por organização, não por empresa ou pedido.

## Snapshots e limites de contrato

- Opções e itens congelados: guarda ORM e triggers PostgreSQL bloqueiam UPDATE.
- Pedido: campos congelados só permitem atualização de status, versão e timestamp no banco.
- Cotação: critérios/request_key/contexto não mudam; identidade externa e resposta só podem
  ser preenchidas uma vez. Novo critério exige novo registro/chave, conforme referência L185–L186.
- JSONB preserva o conteúdo, não a ordem de chaves/bytes do JSON. Assinatura de webhook sobre bytes
  exatos pertence ao receptor futuro, não a essa persistência.
- `manual_only`, `demonstration_only` e estimativa `weight_only` impedem contratação automática.
  Mesmo flags falsas não provam elegibilidade: o guard retorna TODO-CONTRACT, sem executar integração.
- `external_status` é string opaca separada do enum local. Não se inventam enums completos da Packsenvios.
- Fixtures em `backend/tests/domain_fixtures.py` são declaradamente **sintéticas**, não HTTP observado.
- TODO-SCHEMA-DETAIL (06/13/14/17): detalhes internos de snapshots/labels/eventos/importação não estão
  integralmente publicados no guia; os campos JSON tipados são armazenamentos de evidência, não schemas
  completos inventados. TODO-IMPORT-DEDUPE (13): derivar chave contextual incluindo titular/empresa/unidade;
  a unicidade do registro local está pronta, sem alegar reproduzir todo comportamento remoto.

## Transições explícitas (todas locais)

Método `transition()` e validador de atribuição direta usam um grafo por entidade.
Transição impossível ou enum de outro ciclo gera `TransitionError`; repetir o mesmo estado é idempotente.
Enum/check SQL restringe valores locais; a sequência do grafo é aplicada pelo ORM, não por trigger SQL.
Todos os registros com ciclo e estoque possuem versão para detectar atualização concorrente obsoleta.

- Cart: `active → checkout_pending → checked_out`; pode abandonar; pode voltar de checkout_pending
  para active quando os critérios mudarem (serviço futuro também deverá aumentar a revisão).
- Checkout: `created → quoting → quoted → confirmed`; falha/indisponibilidade/revisão fiscal
  são estados locais distintos e podem terminar em invalidated.
- Quote: `requested → received/failed/invalidated`; resposta recebida pode ser invalidated.
- Order: `payment_pending → paid_simulated/payment_declined/cancelled`; pagamento não é externo.
- PaymentSimulation: `pending → approved/declined`; estados finais não voltam a pending.
- Fulfillment: `pago_simulado → separando → embalado`; ramo simulado segue para
  `expedido_simulado → entregue_simulado`; ramo operacional passa por pronto_para_importacao/
  importacao_pendente. Resultado remoto **não** se converte automaticamente em entrega simulada.
- ShipmentImportBatch: preparação/upload/validação/confirmação/importação/despacho/conclusão locais;
  failed não tem retry cego. Fluxos de resume/reconciliação serão implementados no 13/14.

## Migrations e testes

`backend/migrations/versions/0001_local_domain.py` é uma definição congelada das 16 tabelas,
índices, FKs, unicidades, checks e funções/triggers. Não importa os modelos vivos para executar
upgrade/downgrade. Downgrade remove dependências na ordem inversa e funções próprias.

Testes PostgreSQL só aceitam URL explícita de loopback ou binários locais. Cada teste cria/remove
um schema `freight_test_<uuid>` próprio, sem migrar public ou tabelas existentes. A fixture portátil
inicia/encerra seu cluster temporário e não registra serviço no Windows. Sem configuração,
integração PostgreSQL é SKIP explícito; `PersistenceCheck` exige configuração.

## Evidências efetivamente executadas

Data: 08/10/2026. Dependências instaladas: SQLAlchemy 2.0.54, Alembic 1.20.0,
psycopg/psycopg-binary 3.3.6. Lockfile atualizado por `poetry lock` + `poetry sync`.

Docker continuou indisponível (`dockerDesktopLinuxEngine` inexistente). Para não substituir
PostgreSQL por SQLite nem alegar testes não executados, foi usado **PostgreSQL 17.6 real**:
binários portáteis obtidos do distribuidor EDB e extraídos em
`C:\Users\jacks\AppData\Local\Temp\opencode\freight-domain-pg-20261008`.
Nenhum serviço do Windows foi instalado. As conexões foram exclusivamente de loopback.

| Comando / verificação | Resultado efetivo |
|---|---|
| `poetry lock` / `poetry sync` | PASS; 8 novas dependências instaladas |
| `initdb` / `pg_ctl start` | PASS; cluster privado local para geração de migration |
| `poetry run alembic revision --autogenerate --rev-id 0001 -m local_domain` | PASS; migration gerada em banco privado, revisada e completada com triggers |
| `poetry run ruff format .` / `poetry run ruff check .` | PASS na rodada final |
| `poetry check --lock` | PASS |
| `dev.ps1 Check` com `TEST_POSTGRES_BIN` | PASS; **41 testes backend**, sem SKIP ou warnings na rodada final |
| Integração PostgreSQL incluída acima | **26 testes**: todos os modelos, UUID/UTC, unicidade, FKs, valores inválidos, snapshots, IDs, rollback, concorrência e migrations |
| Testes domínio/offline incluídos acima | **13 testes**: transições, atribuição direta, flags de contratação, UTC e SQL de upgrade/downgrade |
| Smoke backend incluído acima | **2 testes** de bootstrap/configuração e ausência de exposição de segredo sintético |
| Ciclo Alembic dentro de schemas próprios | PASS; upgrade → check sem drift → downgrade base → upgrade → check sem drift |
| ESLint / Prettier / typecheck / Vite build | PASS; frontend não modificado pela feature |
| Vitest | PASS; **4 testes** |
| Verificador contratual | PASS; 14 métodos/rotas/abilities/referências e 3 JSONs válidos |
| `dev.ps1 Smoke` | PASS; inicialização HTTP FastAPI/Vite e proxy local preservados |
| `docker compose config --quiet` | PASS; não implica build/execução Docker |
| `git diff --check` | PASS; apenas avisos de normalização LF/CRLF do Git |
| Consulta local de schemas de teste remanescentes | **0** |
| `pg_ctl stop` + conferência de processos próprios | PASS; **0 processos PostgreSQL próprios remanescentes** |

Para a execução completa foi definida a variável:

```powershell
$env:TEST_POSTGRES_BIN = 'C:\Users\jacks\AppData\Local\Temp\opencode\freight-domain-pg-20261008\pgsql\bin'
# Na raiz do repositório:
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\dev.ps1 Check
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\dev.ps1 Smoke
```

A fixture iniciou/encerrou seu próprio cluster temporário nessa rodada; schemas de integração
foram isolados por teste. O cluster auxiliar usado para gerar a revision também foi encerrado.

### Correções encontradas durante a execução

- Nomes gerados de duas unicidades de cotação colidiam; receberam nomes específicos e foram
  conferidos pelas migrations e pelo teste de namespace/request_key.
- Uma asserção offline esperava remover a tabela de controle Alembic; corrigida para as
  16 tabelas de domínio, mantendo o controle de versão vazio como o Alembic faz.
- A comparação em schema isolado identificou falsamente a tabela Alembic como tabela a remover;
  apenas essa tabela de controle foi excluída do autogenerate. Comparação de todas as entidades passou.
- Captura de pipes do `pg_ctl` no Windows bloqueou uma rodada até timeout de 120 s; o runner
  passou a gravar stdout/stderr em arquivo local e usar timeout próprio. A rodada gerenciada final passou.
- Erros de sintaxe/quoting em comandos auxiliares PowerShell foram corrigidos antes da verificação
  final e do encerramento do cluster; não alteraram dados da aplicação.

## Limitações e próximo prompt

Nenhuma integração HTTP Packsenvios, fila, webhook, pagamento real ou migration externa foi executada.
Docker build/runtime seguem não comprovados enquanto o daemon estiver indisponível; os testes de
persistência **não** dependem dessa validação Docker e foram executados em PostgreSQL real local.
Não foram adicionadas APIs comerciais ou reserva de estoque automática; pertencem às próximas etapas.

**Próximo prompt desbloqueado: 04 — API de catálogo e estoque.**
