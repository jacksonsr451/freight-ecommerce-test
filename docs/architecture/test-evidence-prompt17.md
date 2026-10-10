# 17 — Testes end-to-end e evidências

> **Registro histórico pré-prompt 19:** os comandos foram executados com pytest; os atuais usam
> jsr-testrunner. Veja `docs/development-testing.md`.

Execução final: **10/10/2026** · raiz `E:\Softwares\joao\tests` · Windows/Edge local.

## Comandos executados

```powershell
$env:TEST_POSTGRES_BIN = 'C:\Users\jacks\AppData\Local\Temp\opencode\freight-domain-pg-20261008\pgsql\bin'
.\scripts\dev.ps1 -Task Check
npm.cmd run test:layout  # executado em frontend/
```

`Check` executa BackendCheck (Poetry/Ruff/pytest/contratos), FrontendCheck (ESLint/Prettier/Vitest/
TypeScript/build) e o validador documental da matriz de contrato.

## Matriz de evidências

| Área | Resultado | Evidência / detalhe |
|---|---|---|
| Backend unitário + PostgreSQL | **PASS — 280 testes** | Inclui API de catálogo/carrinho/checkout, quotes, pedidos, dispatch/tracking mocks, diagnósticos, webhooks e persistência. |
| PostgreSQL/migrations | **PASS** | Cada fixture cria schema aleatório próprio e aplica Alembic até `head`; testes removem somente o schema criado por eles. Nenhum banco compartilhado/externo foi migrado. |
| Frontend Vitest/Testing Library | **PASS — 54 testes / 9 arquivos** | Inclui jornada do checkout, pedidos, administração/importação, snapshots, diagnósticos e erros. |
| Playwright jornada real local | **PASS — Edge + Vite + Uvicorn + PostgreSQL** | Catálogo → carrinho (POST/PATCH/DELETE) → checkout → cotação sintética → seleção local → pedido/pagamento simulado → fulfillment administrativo `pago_simulado` até `entregue_simulado` → histórico/tracking simulado. Verifica ausência de Bearer e tráfego externo do navegador. |
| Playwright layout | **PASS — 5 testes** | 320/390/768/1280 px, overflow, teclado e aviso de compra simulada. |
| Ruff / ESLint / Prettier / TypeScript / build | **PASS** | `Check` completo. |
| Matriz contratual | **PASS** | 14 rotas Packsenvios: método, ability e linha fonte conferidos; 3 exemplos JSON sintaticamente válidos. As operações sem OpenAPI/código continuam explicitamente marcadas na matriz. |
| HTTP real Packsenvios / cotação real | **SKIP** | Nenhuma chamada externa foi feita; transportes dos testes são sintéticos/mock. |
| Despacho real / tracking Elite / webhook entregue | **SKIP** | Sem conexão homologada, worker/filas ativos ou destino público verificado. Os testes cobrem somente adapters `MockTransport`. |
| Runtime Docker Compose | **SKIP** | A jornada usa PostgreSQL portátil em loopback e schemas temporários; não foi necessário subir containers. |

### Cobertura de erros e invariantes

- `401/403/404/409/422/429/503`: exercitados em testes de autorização, catálogo/carrinho, client, importação e webhook. `Retry-After` é verificado sem retry indevido de despacho/refresh.
- Idempotência e concorrência: double-submit de pedido, disputa por estoque, upload repetido deduplicado, replay de webhook por `id` e conflitos de ID/corpo.
- Modos: compras/pagamento/pedido locais permanecem simulados; modo mock não envia import/dispatch/tracking; quote mock usa fixture sintética. Modo real não implica teste HTTP real.
- Segredos/redaction: token, chave de assinatura, documento, e-mail, endereço, corpo HTTP e snapshot completo não aparecem no diagnóstico/log. Relatório contém IDs operacionais, status normalizados e resumos redigidos.
- Webhooks: testes cobrem HMAC sobre bytes exatos, assinatura inválida, timestamp antigo, replay, ordem invertida, contexto errado e worker indisponível com recibo durável antes de `202`.

## Iterações e lacunas mantidas

Durante o ajuste da jornada live, uma execução inicial detectou uma chave local duplicada no ambiente sintético; após removê-la, a execução seguinte mostrou que o teste clicava na próxima ação do carrinho antes de o botão sair do estado ocupado. O Playwright agora aguarda o botão habilitado. Uma execução intermediária do `Check` também detectou formatação Prettier pendente no script live. Esses pontos foram corrigidos e a execução final completa passou.

`docs/architecture/contract-matrix.md` e os TODOs específicos registram as lacunas que não podem ser inventadas: cabeçalhos literais do modelo oficial; formato/unidade do header timestamp de webhook (o receptor fica desligado sem configuração explícita); estados aninhados não especificados; e falta de homologação/worker externo. `SKIP` significa não executado, não sucesso presumido.
