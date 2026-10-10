# 06 — Cliente Packsenvios e configuração segura

> **Registro histórico pré-prompt 19:** resultados de pytest abaixo são da rodada original; hoje a
> suíte Python usa jsr-testrunner. Veja `docs/development-testing.md`.

Fonte contratual lida integralmente: `docs/reference/gestao-frete-integracao-ecommerce-teste.md`.
Adapter em `backend/src/freight_ecommerce/freight/`, sem dependência de Cart/ORM/FastAPI.
Compartilha apenas a localização do `.env` da raiz com a configuração do backend.
HTTPX 0.28.x foi promovido de dev dependency para runtime, para funcionar no container `--only main`.

## Recorte e rastreabilidade

| Código | Fonte / contrato |
|---|---|
| `create_quote` | POST `/api/v1/freight/quotes`, JSON, HTTP 200 inclusive sem oferta; ability write (L35/L54–L73) |
| `get_quote` | GET `/api/v1/freight/quotes/{quote_request}`, data.id UUID, contexto query, sem body; ability read (L37/L148–L157) |
| Headers | Bearer e Accept JSON; Content-Type JSON para POST (L19) |
| Contexto | Empresa/unidade de backend; não aceitar workspace_id/shipper_account_id nem trocar tenant após 403 (L23–L27/L184) |
| Idempotência | Mesma chave/critérios repete snapshot; divergência 422 request_key (L185–L186) |
| Resultado | Envelope data, options preservadas, sem ID genérico de opção ou ordenação assumida (L121–L180) |
| HTTP/retry | 401/403/404/409/422/429/503, Retry-After; rede/5xx não provam ausência de efeito (L286–L311) |

Não implementa bulk, selection, contract, import, financeiro ou fallback Postagem/TMS.
Nenhuma oferta manual pode ser contratada automaticamente porque não existe operação de contratação
neste adapter. Seleção no pedido será referência local a snapshot no motor 07.

## Configuração

`FreightSettings` lê somente variáveis server-only `FREIGHT_*`; vazio vira ausência quando opcional.
Modo default mock, real exige URL/key/empresa explicitamente configuradas. Isso é política do SDK da
loja: a API possui contexto condicional/legado, mas a loja escolhe empresa explicitamente para evitar ambiguidade.
Unidade não é inventada: optional UUID, conforme portal/autoridade e origem. O próprio provedor revalida grants.
Chave é SecretStr excluída de repr; mensagens de validação ocultam valores de entrada.

URL base deve apontar à aplicação, não /api/v1/freight. Usuário/senha, query, fragmento, credencial
embutida e caminhos do grupo freight são rejeitados. Política do SDK: HTTPS, exceto HTTP loopback;
não é uma garantia de ambiente real disponível. Proxy por variáveis de ambiente e redirects são
desabilitados para não encaminhar Bearer implicitamente a outro destino. Certificado TLS não é desabilitado.

Configuração de unidade/empresa é fixada no POST e GET; request backend com contexto diferente é
recusado antes de enviar HTTP. Origem explícita ainda precisa ser coerente com a operação (L27).
GET permite consulta sem definir origem. Real sem unidade requer origem em config/request para criação.

## Payload canônico e retries

Request tipado/frozen, volumes em tupla de modelos frozen e PreparedQuote com bytes imutáveis.
CEP/peso são normalizados conforme cotação simples (L73), peso enviado como string decimal com 3 casas,
centavos inteiros estritos. Dimensões/volume_count e soma dos gramas são validados (L63–L71).
Campos opcionais nulos são omitidos consistentemente. Invoice_count existe somente no recorte simples.
Sem dimensões permanece estimativa weight_only; volumes individuais não dispensam dimensões de cubagem.
Essa validação não inventa política de embalagem ou tabelas tarifárias; cabe ao motor 07.

PreparedQuote mantém request_key e fingerprint local dos critérios; não gera chave de retry.
É revalidado antes de envio para recusar bytes/contexto/fingerprint adulterados. A mesma sequência de bytes
é reutilizada em timeout/erro de transporte/429/503, no máximo max_attempts (default 2, limite 3).
401/403/404/409/422, protocolo inválido, redirect e demais status não têm retry automático.
Retry-After aceita segundos inteiros ou HTTP date; se exceder orçamento total de espera (default 5 s),
erro devolve tempo ao chamador, sem truncar para tentar antes. Ausente/inválido: backoff 0.1/0.2 s.

TODO-PERSIST-PREPARED (07): persistir chave e payload antes de HTTP, por namespace da organização,
recarregar os mesmos critérios após restart/timeout. O cliente não substitui unicidade/transação do banco.
Trocar critério exige nova chave. Mock mantém replay em memória do transport, não promete durabilidade
entre processos; o teste de 422 divergente usa esse mesmo servidor sintético.

## Respostas e lacunas

Price é inteiro obrigatório por oferta: ausência/float/null não vira preço zero. Prazo, nomes, flags e
campos opcionais podem faltar/null. `manual_only` ausente permanece **None**, não false.
Status externo é string não vazia aberta para GET histórico (ex. selected), não enum local inventado.
QuoteSelection preserva histórico sem implementar seu POST. Se quoted vier com options vazias,
retorna erro de protocolo conforme divergência OpenAPI L321, não fallback fictício.
Criteria não deve conter request_key. Contexto retornado é conferido quando presente/configurado.

TODO-SCHEMA-RESPONSE (07/17): private_carrier_id/versionamento/composição/cubagem/assumptions e campos
internos não possuem schema completo no guia. São JsonValue tipados e campos adicionais JSON preservados,
não formatos adivinhados. Rate_table_id/carrier_workspace_id e company/location são UUIDs onde documentados.
Nenhum método assume options[i].id ou transforma private_carrier_id em carrier_workspace_id.

## Erros e logs

FreightError retém apenas código **local**, mensagem fixa segura, status HTTP, Retry-After normalizado
e nomes de campos conhecidos; não retém request/response/raw message/body ou contexto de exceção HTTP.
Conflito request_key é identificado pela mensagem contratual documentada; demais mensagens Laravel
não são assumidas constantes ou devolvidas cegamente. 403 nunca provoca tentativa com outra empresa.

Logs próprios: allowlist operação/método, tentativa, outcome e status. Nada de headers, URL, CEP,
payload, credencial ou resposta. Logs HTTPX/httpcore durante a chamada são substituídos por evento opaco
via filtro ContextVar; níveis/handlers e diagnósticos de chamadas fora do adapter não são alterados.
Nenhuma chave fica armazenada no filtro global. Não publicar dumps/repr de payloads server-only em UI.
Motor 07 deverá devolver somente campos públicos/ref interna, não config ou resposta bruta.

## Mock e evidências

SyntheticQuoteTransport e `tests/fixtures/freight/` são **explicitamente sintéticos**. Preço 2590,
prazo 3, transportadora e snapshots são exemplos, não cálculo tarifário ou homologação.
Cenários quoted/unavailable/fiscal_review são selecionados por config, não por lógica fiscal inventada.
Mock usa token sintético próprio, nunca a chave real do ambiente, e transport sem DNS/socket.

### Resultados efetivamente executados

Execução: 09/10/2026; referência contratual inspecionada em 08/10/2026.

| Comando / verificação | Resultado efetivo |
|---|---|
| `poetry lock` / `poetry sync` | PASS; HTTPX 0.28.1 agora runtime; sem necessidade de baixar novos pacotes |
| `poetry check --lock` | PASS |
| `poetry run ruff format .` / `poetry run ruff check .` | PASS na rodada final |
| `pytest tests/test_freight_client.py -x -q` (rodada inicial) | 61 PASS |
| `pytest tests/test_freight_client.py tests/test_freight_protocol_failures.py -q` | **71 PASS**, totalmente HTTP mock/offline |
| `dev.ps1 Check` com PostgreSQL local disponível | **199 PASS backend**, sem SKIP ou warnings na rodada final |
| Regressão de loja/persistência incluída acima | **128 PASS**; 104 testes PostgreSQL real local e schemas próprios, incluindo migrations reversíveis |
| ESLint / Prettier / TypeScript / Vite build | PASS |
| Vitest | **4 PASS** |
| Validação da matriz contratual | PASS; 14 métodos/rotas/abilities/referências e 3 exemplos JSON válidos |
| `dev.ps1 Smoke` | PASS; FastAPI/Vite e proxy local inicializados e encerrados |
| `docker compose config --quiet` | PASS; não comprova runtime/build Docker |
| `git diff --check` | PASS; apenas aviso Git de normalização CRLF/LF do lockfile |
| Conferência de processos PostgreSQL próprios ao terminar | **0** |

Os 71 testes novos cobrem os três estados de cotação, headers, URI/query/body, UUID consultável,
contexto configurado, normalização/volumes/unidades, campos opcionais/unknown JSON, timeout de POST/GET,
timeout após persistência com replay do snapshot original, replay idêntico e 422 divergente, todos os
HTTPs exigidos, Retry-After em segundos/data, orçamento total e espera longa sem tentativa antecipada,
redirect bloqueado, resposta inconsistente/JSON inválido, imutabilidade/adulteração de payload,
credenciais ausentes, URLs inválidas e logs/erros sem token mesmo com diagnósticos privados simulados.
Mocks foram isolados de variáveis FREIGHT_* reais do processo para impedir rede/configuração acidental.

Comando da rodada agregada, a partir da raiz do projeto:

```powershell
$env:TEST_POSTGRES_BIN = 'C:\Users\jacks\AppData\Local\Temp\opencode\freight-domain-pg-20261008\pgsql\bin'
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\dev.ps1 Check
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\dev.ps1 Smoke
```

As primeiras verificações Ruff apontaram uma mensagem longa e um import sem uso; corrigidos antes
da rodada final. Todas as rodadas de testes executadas nesta feature passaram.
Alterações não commitadas da etapa 05 foram preservadas; nenhum commit/push foi executado.

## Limitações e próximo prompt

- **Nenhuma chamada HTTP real Packsenvios** ou emissão/uso de credencial real nesta execução.
  Modo real foi testado somente com transport interceptado; autorização, URL disponível, quotas,
  transportadoras/tabelas e homologação permanecem não verificadas.
- Processamento assíncrono, contratação, pagamento, despacho e webhooks externos não foram executados.
- Configuração e dependência runtime do container foram atualizadas; runtime/build Docker não executados.
- Não há novas rotas públicas de frete nem alteração do frontend. Motorização de carrinho,
  persistência do PreparedQuote e respostas públicas mínimas ficam para o 07.
- Snapshot interno e resposta bruta permanecem server-only; nenhum Bearer foi enviado ao navegador.

**Próximo prompt desbloqueado: 07 — Motor de cotação e snapshots.**
