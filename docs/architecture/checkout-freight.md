# 10 — Checkout e comparação de fretes

Fonte externa usada: `docs/reference/gestao-frete-integracao-ecommerce-teste.md`, L7–L9, L19–L27,
L33–L39, L54–L73, L121–L180 e L184–L188. Não foram inferidos campos, endpoint ou permissões externos.

## Implementação

- Formulário comprador (nome/e-mail) e endereço BR (CEP, rua, número, complemento, bairro, cidade, UF).
  Não coleta CPF/CNPJ nem documentos fiscais para cotação.
- `PUT /api/carts/{cart_id}/checkout-details` pertence à **loja** e grava somente no carrinho anônimo.
  Não cria Customer/Address nem documento/identidade fiscal. E-mail é validado pela biblioteca
  email-validator; campos extras são recusados.
- Backend salva dados e chama apenas o orquestrador local `POST /api/carts/{id}/freight-quotes`.
  O cliente não define preço, destino comercial fora do endereço, company/location/contexto ou request_key.
- Motor (07) deriva valor/gramas/dimensões e chave, persiste payload/snapshots, depois usa adapter 06.
  Browser recebe projeção segura e UUID interno de snapshot.
- GET interno consulta snapshot e valida revisão. POST `/selection` interno atualiza só o vínculo
  local; não chama Packsenvios `/selection`, `/contract`, compra, pagamento ou envio.

## Estados e seleção

- Checkout não permite cotar carrinho vazio, sem endereço, inativo ou com falta de estoque.
- Modo default `equal_volumes`; geometrias divergentes retornam revisão de embalagem. Alternativa
  `weight_only` explícita é estimativa e opção desabilitada para fechamento.
- `quoted` mostra zero ou mais opções. Cada opção expõe referência interna, preço, prazo em dias,
  nome se informado, `manual_only`, `demonstration_only`, modo de revisão e aviso local.
- `manual_only:true`/`demonstration_only:true` não habilitam contratação; a UI afirma escolha local.
  Flag faltante permanece desconhecida e exige revisão, nunca é interpretada como false.
- `unavailable` e `fiscal_review` são vazios distintos sem inventar frete zero. `pending` acompanha
  referência interna; 401/403/409/422/429/502/503/504 exibem mensagens controladas.
- `Retry-After` é validado e apresentado como cooldown; não há retry de quote em UI ou repetição
  de efeitos externos. Refresh é explícito e gera nova request_key/snapshot.
- Nenhuma `options[i].id`, ordenação fixa ou `rate_table_id` universal é presumida.

## Invalidação e cache do frontend

Buyer/endereço só são enviados no PUT quando formulário válido e usuário clica “Salvar dados e cotar”.
Fingerprints/revisão do carrinho incluem nome/e-mail/endereço; mudança de comprador também invalida
quote: é critério comercial/contextual, não regra externa. Ao editar, dirty oculta ofertas/seleção
imediatamente; save muda revisão, invalida snapshots anteriores no servidor e só então inicia cotação.
Seleção só é liberada para referência presente em quote/cart revision atuais.

TanStack Query não repete mutations; após erro, consulta o carrinho e oculta/revalida quote. GET
pendente tem estados próprios. A gravação de checkout e cotação ocorrem em transações separadas:
checkout persistido continua em caso de timeout (request key/payload ficam no backend); usuário pode
retomar sem recriar identidade. Seleção local não vira order/payment.

`CheckoutDetails` atualiza cart e, caso já haja CheckoutAttempt vinculado, tentativa deve ser ajustada
ou invalidada coerentemente antes de cotar. No fluxo guest existente não há tentativa; motor mantém
quote ligada diretamente ao cart. TODO-BUYER-ATTEMPT-BINDING permanece para prompt 11 (criação legítima
de CheckoutAttempt ao confirmar, sem dados fiscais inventados).

## Limites externos mantidos

Pré-requisitos reais (URL autorizada, chave, abilities `freight:quotes:write/read`, grants do titular,
empresa/unidade/tabelas) não são confirmados por esta UI. Sem ambiente, testes de usuário usam modo mock
com fixtures sintéticas; modo Real exige configuração server-side correta.
Modo Real exibido não é prova de conectividade/homologação. Bearer, base URL e IDs configurados nunca
são serializados para frontend. Compra/pagamento/pedido permanecem locais e simulados.

## Evidências executadas

Execução: 09/10/2026. Dependência nova backend: `email-validator` 2.3.0 (lock Poetry atualizado),
para validar endereço de e-mail do comprador; dados de teste são sintéticos.

| Comando / verificação | Resultado efetivo |
|---|---|
| `poetry run ruff format .`, `poetry run ruff check .`, `poetry check --lock` | PASS |
| Testes checkout + motor dirigidos | **28 PASS** com PostgreSQL 17.6 em schemas descartáveis e HTTP mock |
| Validação de API de comprador/endereço | E-mail, nome, CEP inválido/numérico, campos extras e persistência atômica: PASS |
| Seleção/invalidação API | Comprador/endereço salvo no cart guest; seleção local; no-op preserva revisão; mudar buyer/endereço incrementa revisão e invalida quote |
| Vitest/Testing Library | **40 PASS**: 5 arquivos, incluindo 8 casos novos de checkout |
| Playwright/Edge desktop/mobile | **5 PASS** (shell 320/390/768/1280, formulário, teclado) |
| TypeScript, ESLint, Prettier, Vite build | PASS na última rodada |
| Matriz de contrato | PASS; nenhuma rota externa nova adicionada |

`dev.ps1 Check` executou a suíte agregada: **242 testes backend PASS** (237 PostgreSQL marcado e
5 sem banco); `dev.ps1 Smoke` e `dev.ps1 LayoutCheck` também passaram. Vitest tem **40 testes PASS**
(5 arquivos); Edge real, **5 testes PASS** em 320/390/768/1280 e navegação por teclado.

`pytest tests/test_checkout_details.py tests/test_quote_engine.py tests/test_store_browser.py` passou
com PostgreSQL real local. O browser flow verifica catálogo/carrinho/checkout/mock/seleção local,
snapshot manual/demonstrativo, ausência de Order/Payment e reserva, tráfego local sem Authorization
nem conexão externa. Screenshot `checkout-live-mobile.png` foi gerado no tmp_path e inspecionado;
mostra opções, avisos manuais/demonstrativos, subtotal server-side e seleção local.

### Estado de verificação desta tarefa

Nenhuma chamada de produção/homologação Packsenvios foi executada. Estados são respostas mock; não
provam disponibilidade real nem elegibilidade comercial. O motor 07 e os schemas externos continuam
restritos à referência. Docker runtime não foi validado.

Uma rodada de browser falhou antes da verificação final porque o teste usou `.check()` (API de checkbox/
radio) em botão de seleção; substituído por click acessível. A nova falha final encontrada por asserção
de banco era a expectativa antiga de carrinho vazio após o teste também executar checkout; ajustada para
validar item, seleção persistida, nenhum pedido/pagamento e zero reserva. Rodada live passou depois.
O lint também apontou uma asserção com campo de API não narrowing em TypeScript; corrigida. Erros e
correções estão explicitados, sem suppressões de tipos/lint.

**Próximo prompt desbloqueado: 11 — Pagamento simulado e pedidos.**
