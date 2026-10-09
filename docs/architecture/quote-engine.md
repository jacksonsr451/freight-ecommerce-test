# 07 — Motor de cotação e snapshots

Fonte contratual: `docs/reference/gestao-frete-integracao-ecommerce-teste.md`, lida antes da integração.
L54–L73 orientam unidades/volumes; L121–L180 respostas; L184–L188 idempotência, fonte servidor e escolha local.
Nenhum endpoint, payload, status ou permissão adicional de Packsenvios foi inventado.

## API local e projeção

POST quote, GET persistido e POST selection sob `/api/carts/{cart_id}/freight-quotes`.
Não são os endpoints externos `/api/v1/freight/...`: somente o adapter 06 chama POST cotação.
Seleção é gravação local em FK de snapshot, não chamada de contratação/seleção Packsenvios.
Cliente manda revisão/política/ref, jamais preço, peso, dimensões, total, company/location ou request_key.

Resposta: quote_reference UUID interno, revisão, status **local/projeção**, modo mock/real,
weight_only, options e selected_option_reference. Opção expõe referência interna, nome opcional,
price_cents, deadline_days opcional, manual_only/demonstration_only opcionais, weight_only e
manual_review_required. Não expõe request/criteria/response, IDs privados, chave ou composição bruta.
Echo de credencial/Bearer no nome do provedor é omitido da projeção pública, sem alterar o payload privado.

Estado remoto quoted/unavailable/fiscal_review é preservado na resposta persistida. Pending/failed/
invalidated são estados da loja, não alegações de cancelamento ou processamento da Packsenvios.
Ofertas ausentes não geram zero/fallback. Prazo continua em dias da tabela, sem data/dias úteis inventados.

## Política de volumes

Política demonstrativa: **uma unidade de produto = um volume final**, com as medidas cadastradas.
Não se soma altura, não se constrói caixa máxima, não se infere embalagem ou margem/cubagem.
Peso/dimensões/valor vêm da mesma consulta servidor do carrinho. Ainda é premissa de demonstração,
não evidência de embalagem física homologada. Adequação comercial precisa ser validada no ambiente real.

- equal_volumes: todas as unidades têm a mesma tupla ordenada comprimento/largura/altura.
  Peso unitário pode variar: volumes[] captura cada peso/dimensão, soma exata e volume_count explícito.
  Tripletas rotacionadas não são assumidas equivalentes. Dimensões agregadas repetem a geometria comum.
- Divergência geométrica é 422 unequal_volumes. Não usar volumes[] como dispensa de dimensões agregadas
  para cubagem/contratação, conforme L71. Nenhuma cotação HTTP é enviada nesse caso.
- weight_only explícito: só peso total/valor/destino/contexto; omite dimensões/volumes/volume_count.
  Estimativa é persistida e marcada; seleção para fechamento de pedido é recusada.
- Gramas inteiros → string kg com exatamente 3 casas, sem float. Valor é centavos inteiros.
  SDK valida <=50.000 kg, <=100.000.000 centavos, dimensões 1–300 cm, 1–1000 volumes e soma/quantidade.
  Destino exige string canônica de 8 dígitos e preserva zeros; nenhum CEP/fiscal/volume falso é criado.

## Persistência e guest quotes

Migration 0003 guarda Quote diretamente no Cart, permitindo checkout_attempt_id NULL antes de haver
comprador/Address. Não cria Customer/email/CPF/CNPJ fictício para cotação. Vínculo posterior com
CheckoutAttempt deve pertencer ao mesmo Cart (FK composta) e pode ser preenchido somente uma vez.
Order continua exigindo cliente/tentativa reais locais e vínculo coerente no fechamento futuro.

Quote guarda bytes BYTEA canônicos, fingerprint dos critérios e do carrinho, modo/namespace,
UUID request_key, ID remoto separado, resposta JSONB, lease, erro seguro/cooldown e seleção local.
Snapshot guarda índice/UUID próprio e JSON completo com preço/flags; não assume options[i].id nem
rate_table_id único (uma tabela pode gerar mais de uma oferta). Campos ausentes ficam NULL, não valores
falsos/nome inventado. Imutabilidade de payload/IDs/response/criteria é aplicada por ORM e PostgreSQL.

JSONB preserva conteúdo sem garantia de ordem/bytes da resposta. Request HTTP tem **bytes exatos**
persistidos; DTO mantém JSON estruturado do resultado (incluindo extras), não comprova raw HTTP original.
Nova FK da seleção garante que o snapshot pertence à cotação, inclusive em escrita SQL direta.

Reversão: 0003 → 0002 só restaura NOT NULL/tamanho legados quando dados são compatíveis. Se houver
quote guest, carrier/flags NULL ou nome >160, downgrade recusa explicitamente e transacionalmente;
nunca fabrica clientes/flags/nome para adaptar histórico. Em schemas descartáveis vazios, todo o ciclo
upgrade → downgrade base → upgrade é testado e metadata deve permanecer sem drift.

## Transações, cache e concorrência

1. Lock Cart, validar revisão, dados/estoque e recalcular fingerprint. Mudança de catálogo provoca
   invalidação/refetch antes de cotar. Nenhuma reserva de estoque é feita.
2. Contexto empresa/unidade/origem vem do adapter backend. Cache compara fingerprints e namespace
   de modo/URL/organização, sem usar a credencial como tenant ou como dado de request.
3. Critérios atuais idênticos retornam resposta/snapshots locais já salvos, sem novo HTTP ou recálculo
   de tabela externa. Refresh explícito, mudança de catálogo/endereço/itens ou contexto exige novo UUID.
4. Nova tentativa REQUESTED é commitada com os bytes antes do HTTP. Lease com token/deadline impede
   dois clientes iniciarem a mesma chamada; concorrente recebe 202 pending, mesma quote_reference.
5. Lock/connection da transação são liberados durante await HTTP. Timeout/rede/429/503/protocolo incerto
   conserva chave/payload e estado REQUESTED para replay. Erros definitivos geram FAILED, exigindo
   correção/refresh explícito. IDs jamais são confundidos com request_key.
6. Retry-After gera cooldown persistido por namespace, inclusive após mudar critério/refresh, evitando
   tentativa antecipada por uma chave nova. Cache já recebido pode ser lido sem HTTP durante cooldown.
7. Resposta: novo lock Cart, checar fingerprint/contexto/lease/status. Gravar resposta/ID/snapshots
   atomicamente, então responder. Resposta de critério antigo fica no histórico INVALIDATED, sem
   ser revivida; opções antigas não são publicadas/selecionáveis. Worker que perdeu lease não sobrescreve.
8. Se a gravação do resultado falha, tentativa anterior continua durável; após lease expirar, replay
   usa a mesma chave e bytes. Nunca criar nova chave automaticamente por resposta incerta.

Leases são retomáveis por POST após expiração, sem worker/scheduler ativado. Cache não presume que
grants/tabelas/oferta real continuam atuais para contratação, que não é implementada. Revalidar na
confirmação (11) e na operação externa autorizada. Scope local deve ser configurado consistentemente
quando credenciais apontarem a outra organização; nenhuma discovery Bearer foi presumida.

## Seleção e auditoria

Selecionar requer cart revision/fingerprints/contexto atuais, response quoted e snapshot da mesma
quote/cart. Preço reenviado ou ref de outro carrinho é recusado. Weight-only não fecha pedido.
Manual/demonstration podem registrar escolha **simulada local**, com aviso; nunca contratação automática.
Flags desconhecidas ficam NULL e exigem revisão. Snapshots, resposta e seleção histórica remota não mudam.
Auditoria registra correlação, modo, key/quote IDs, started/succeeded/failed/uncertain e latência/código seguro,
sem headers/credential/raw payload. Persistência privada não é retornada ao browser.

TODO-GUEST-BINDING (10/11): preencher Customer/Address/CheckoutAttempt legítimos ao colher comprador,
validar Cart/revisão/seleção e completar FK uma única vez. Não reusar quote invalidated nem assumir
contratação, documento fiscal ou reserva de estoque por existir cotação.

## Evidências

Execução: 09/10/2026. Bibliotecas instaladas atenderam à feature; nenhum pacote adicional foi
necessário. Modelos/config/carrinho e dependências foram inspecionados antes das alterações.

| Comando / verificação | Resultado efetivo |
|---|---|
| `poetry run ruff format .` / `poetry run ruff check .` | PASS na rodada final |
| `poetry check --lock` | PASS |
| Testes domínio/smoke iniciais | 15 PASS |
| `pytest tests/test_quote_engine.py ... -x -q` (rodada inicial) | 17 PASS com PostgreSQL real + HTTP mock |
| Motor/política/persistência após expansão | 56 PASS |
| `dev.ps1 Check` | **229 PASS backend**, sem SKIP ou warnings na rodada final |
| Motor novo incluído acima | **21 PASS**: request durável, replay, snapshots, estados, concorrência, resposta tardia, rollback, cooldown, contexto e seleção |
| Política nova incluída acima | **9 PASS**: volumes iguais/diferentes, pesos individuais, CEP e limites |
| Regressão incluída acima | **199 PASS**, incluindo adapter HTTP e migrations/constraints anteriores |
| Migration 0003 | Upgrade → downgrade base → upgrade em schema vazio próprio, Alembic check sem drift |
| ESLint / Prettier / TypeScript / Vite build | PASS |
| Vitest | **4 PASS** |
| Verificador contratual | PASS; 14 rotas/métodos/abilities/referências e 3 exemplos JSON válidos |
| `dev.ps1 Smoke` | PASS; FastAPI/Vite/proxy local inicializados e encerrados |
| `docker compose config --quiet` | PASS; não demonstra runtime/build Docker |
| `git diff --check` | PASS |
| Processos PostgreSQL próprios ao terminar | **0** |

Dos 229 testes, 125 rodam em PostgreSQL real (21 motor + 104 anteriores), usando o bundle portátil
17.6 previamente instalado na pasta temporária aprovada. Cada teste usa schema próprio e a fixture
inicia/encerra cluster de loopback, sem migrar dados de public ou ambiente externo.
Chamadas do adapter foram todas interceptadas por transport HTTP mock explícito.

```powershell
$env:TEST_POSTGRES_BIN = 'C:\Users\jacks\AppData\Local\Temp\opencode\freight-domain-pg-20261008\pgsql\bin'
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\dev.ps1 Check
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\dev.ps1 Smoke
```

Um import sem uso, ordem de imports e linha longa foram corrigidos após apontamentos iniciais de
Ruff; uma aplicação de patch sem contexto correspondente foi reaplicada após leitura do arquivo.
Todas as rodadas de testes desta etapa passaram. Nenhum commit/push foi executado.

## Limitações e próximo prompt

- **Nenhuma chamada HTTP real Packsenvios**, compra, pagamento, despacho ou contratação externa.
  Credenciais/grants/URL/tabelas, quotas efetivas e homologação não foram verificadas em rede.
- Aplicar `Migrate` no PostgreSQL local configurado para disponibilizar a 0003 no ambiente de
  desenvolvimento. Tests não populam o banco do usuário nem geram clientes fiscais falsos.
- Runtime/build Docker não foram executados nesta etapa; persistência foi comprovada em PostgreSQL
  portátil real, e configuração Compose foi validada separadamente.
- Binding de comprador, confirmação de pedido/reserva e UI de comparação ainda pertencem aos prompts
  posteriores. A seleção desta etapa é exclusivamente um vínculo local a snapshot.
- O ciclo de schema foi testado vazio; rollback com dados novos exige compatibilidade prévia com
  o modelo legado, recusando dados não representáveis em vez de fabricar valores para satisfazer NOT NULL.

**Próximo prompt desbloqueado: 08 — Frontend base e design system.**
