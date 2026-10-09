# 08 — Shell frontend e design system

Raiz: `E:\Softwares\joao\tests`. Reutiliza React/TS/Vite, lint/format e Vitest do bootstrap.
Escopo: estrutura visual/navegação/estados/validação e diagnóstico público mínimo.
Nenhum endpoint, payload, campo, status ou permissão Packsenvios foi inventado.

## Arquitetura e dependências

- React Router DOM 7 para catálogo, carrinho, checkout, pedidos, diagnóstico e not-found.
- TanStack Query 5: duas chaves compartilhadas, staleTime 30 s, retry automático desabilitado,
  refetch por ação explícita, sem polling/focus-refetch inesperado.
- Zod 4: schemas de health/runtime e CEP; propriedades desconhecidas não chegam à UI.
- Cliente requestInternal: URL relativa same-origin `/api`, bloqueio de URL externa e caminhos
  `/api/v1/freight`, JSON tipado, credentials same-origin, redirects error e sem header Authorization.
- Errors são mensagens locais controladas, sem expor texto privado/HTML/erro raw do servidor.
  Cancelamento preservado para TanStack Query inclusive DOMException de outro contexto JS.
- Nenhum cliente SDK Packsenvios, variável FREIGHT_* ou segredo é importado no frontend.

## Layout e acessibilidade

Freight Lab é identidade local de demonstração, não branding/homologação da Packsenvios.
Tema off-white/navy/verde, tokens CSS, componentes Button/PageHeading/Empty/Loading/Error,
cards, campos com label/help/error e ícones SVG internos. Não há chamadas a fontes/imagens externas.
Grid desktop vira uma coluna em tablet/mobile, com larguras minmax/min-width adequadas.

- Header/navegação/footer compartilhados e marcação semântica, aria-current no link ativo.
- Skip link para main e foco no h1 após mudança de rota; h1 programaticamente focável sem entrar
  desnecessariamente na ordem de Tab. Título do documento acompanha navegação.
- Menu mobile com aria-expanded/controls, 44 px, Escape devolve foco ao controle.
- Foco visível, erro aria-invalid/describedby, alerts/status live e prefers-reduced-motion.
- Formulário CEP aceita string de 8 dígitos preservando zero inicial; inválido recebe foco/erro
  vinculado. Válido informa explicitamente que foi validação local, sem cotação enviada.

Catálogo/carrinho/pedidos são vazios honestos desta base visual, não respostas falsas do banco nem
produtos/preços sintéticos inventados em UI. Conexões comerciais pertencem aos prompts 09–11.
Diagnóstico desta etapa confirma só processo local/configuração, não banco/filas/transportadoras.

## Modo público e segurança

Novo endpoint **interno da loja** GET `/api/runtime`: `{freight_mode: mock|real, purchases_simulated: true}`.
Usa modo do client já configurado quando existir ou configuração backend validada, sem construir
client HTTP ou acessar DB/provedor. Só dois campos são serializados; config inválida retorna 503 seguro.
Não retorna base URL, API key, company/location, namespace, dados de cliente ou payloads.

Badge neutro enquanto verifica; erro vira “Modo indisponível”, não mock assumido. Mock verde identifica
cotação sintética; Real indica config real e compra simulada, sem afirmar disponibilidade externa.
Header/footer reiteram compra/pagamento simulados e ausência de contratação automática.

## Verificação

Vitest/Testing Library + user-event: navegação, foco, estado de página, dedupe Query, modos, loading,
vazio/error/retry, resposta inválida, formulário por teclado, menu/Escape e cliente HTTP seguro.
Playwright: Edge real headless, páginas servidas por Vite, health/runtime interceptados como fixtures
locais explicitamente sintéticas, sem contatos externos; larguras 320/390/768/1280, overflow, navegação,
CEP, skip link e estado Real. Screenshots inspecionados no disco (checkout mobile e catálogo desktop).

Backend tests validam contrato público mínimo e erro seguro, garantindo que nenhum client HTTP
seja criado por runtime. Smoke local confere proxy de health/runtime com backend real iniciado.
Fixtures visuais não comprovam HTTP Packsenvios ou dados de catálogo/banco.

## Resultados efetivamente executados

Execução: 09/10/2026. Dependências novas instaladas por `npm install` e fixadas no package-lock:
react-router-dom 7.18.4, @tanstack/react-query 5.104.1, zod 4.6.5,
@testing-library/user-event 14.6.7 e @playwright/test 1.64.0. Instalação adicionou 10 pacotes e
npm informou zero vulnerabilidades naquele momento. Não houve dependência backend nova.

| Comando / verificação | Resultado efetivo |
|---|---|
| `npm install` | PASS |
| `npm run format` / `npm run format:check` | PASS na rodada final |
| `npm run lint` / `npm run typecheck` / `npm run build` | PASS na rodada final |
| Vitest/Testing Library | **18 PASS** (8 shell/rotas/formulário/estados + 10 cliente interno) |
| `npm run test:layout` / `dev.ps1 LayoutCheck` | **5 PASS**, Edge headless real |
| Layouts 320, 390, 768 e 1280 px | Sem overflow horizontal; navegação/menu, checkout e CEP verificados |
| Keyboard browser | Skip link/main, foco ao mudar rota, menu Escape e CEP Enter verificados |
| Screenshots | Gerados em frontend/test-results e inspecionados: mobile 390 e catálogo desktop |
| `dev.ps1 Check` | **232 PASS backend**, sem SKIP ou warnings na rodada final |
| Contrato runtime novo, incluído acima | **3 PASS**, mock/real/erro e ausência de credenciais/client/network |
| Regressão backend, incluída acima | **229 PASS**, com PostgreSQL real em schemas próprios e HTTP externo mock |
| Validação contratual | PASS; 14 rotas/métodos/abilities/referências e 3 exemplos JSON válidos |
| `dev.ps1 Smoke` | PASS; backend/Vite reais e proxy /api/health + /api/runtime |
| `docker compose config --quiet` | PASS; não comprova runtime/build Docker |
| `git diff --check` | PASS; apenas aviso Git de normalização LF/CRLF em dev.ps1 |
| Artefatos gerados | test-results/dist/node_modules ignorados pelo Git e pelos formatters/lint |
| Processos PostgreSQL próprios ao terminar | **0** |

Comandos agregados executados na raiz:

```powershell
$env:TEST_POSTGRES_BIN = 'C:\Users\jacks\AppData\Local\Temp\opencode\freight-domain-pg-20261008\pgsql\bin'
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\dev.ps1 Format
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\dev.ps1 Check
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\dev.ps1 Smoke
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\dev.ps1 LayoutCheck
```

### Correções encontradas durante execução

Primeira rodada: um teste de cancelamento falhou (DOMException de outro realm não é instanceof
Error da janela), ESLint apontou atribuições não usadas, e TypeScript apontou parâmetro-property
incompatível com erasableSyntaxOnly e QueryClient declarado depois de uso. A checagem de AbortError
foi tornada estrutural, propriedades da classe explícitas e inicialização movida antes do render.
Todos foram corrigidos e nova rodada passou. Não foi suprimida a regra TS/lint para contornar falha.

## Limitações e próximo prompt

- Nenhuma chamada Packsenvios real, Bearer no browser, pagamento, contratação ou migration externa.
- Páginas comerciais são base visual, não consulta real do catálogo/carrinho/pedidos. O diagnóstico
  lê somente API local. Formulário CEP é somente validação local, como sinalizado na tela.
- Testes browser interceptam runtime/health com fixtures sintéticas; o contrato/backend/proxy foram
  verificados separadamente por pytest e smoke local. Isso não comprova homologação externa.
- Backend modo Real é configuração, não conectividade real. Badge representa última leitura/cache
  Query (30 s) e pode ser atualizado no diagnóstico; falha não vira Mock automaticamente.
- Nenhum runtime/build Docker foi executado nesta etapa. Persistência da regressão foi testada
  no PostgreSQL portátil real, sem alterar banco de usuário. Scripts do smoke usam configuração
  sintética no próprio subprocesso, sem modificar o .env ou a configuração global do host.
- Browser layout requer Edge instalado, ou PLAYWRIGHT_BROWSER_CHANNEL=chromium e Chromium Playwright
  disponível. Não foi instalado outro navegador ou alterada configuração global do Windows.

**Próximo prompt desbloqueado: 09 — Frontend catálogo e carrinho.**
