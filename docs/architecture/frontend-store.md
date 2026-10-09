# 09 — Frontend catálogo e carrinho

Raiz: `E:\Softwares\joao\tests`. Reutiliza design system, React Router, TanStack Query e cliente
same-origin da etapa 08. Nenhuma integração, endpoint ou contrato externo Packsenvios foi implementado.

## Jornada e APIs locais

- Catálogo paginado da API, cards com SKU/nome/preço/peso/dimensões/estoque; produto inativo nunca
  aparece em consulta pública, e esgotado tem CTA desabilitado. Não há preço/produto hardcoded na UI.
- Busca e filtro de estoque adicionados ao GET local existente antes de count/paginação; procura
  por nome/SKU case-insensitive com escape literal de `%`/`_`, sem SQL concatenado.
- URL preserva filtros/página, com detalhe `/catalogo/:productId`, voltar e página desconhecida.
- Quantidade validada por formulário (inteiro 1–1000 e limite informativo disponível), feedback seguro.
- Criar/consultar/adicionar/atualizar/remover via APIs Cart 05, subtotal e peso informativo,
  mensagens de estoque, revisão atual e link ao checkout. Compra/pagamento continuam simulados.
- Ilustração SVG não é foto/condição comercial real. Todos os dados dos cards vêm do backend.

## Estado, cache e concorrência

`localStorage` guarda somente UUID do carrinho. `useSyncExternalStore` acompanha referência local e
evento storage de outra aba; falha de storage usa memória. Abrir catálogo/carrinho sem referência
não cria cart no servidor. POST é iniciado apenas por adicionar; criação in-flight é compartilhada.
Customer/endereços, totais, credenciais e configuração Packsenvios não são persistidos no localStorage.
Cache Query em memória contém o Cart validado recebido do backend, sem credentials/configuração.

TanStack Mutation scope serializa writes; controles são desabilitados enquanto há mutação/leitura
necessária. Antes de alterar, fetchQuery staleTime 0 obtém cart revision/estado atuais. Mesmo assim
o servidor mantém locks/checks (outra aba pode mudar entre GET e POST), e 409 não é reexecutado.
Referencia de item só pertence ao próprio carrinho no backend. UUID não é nova permission externa.

**Política otimista:** nenhuma mutação otimista de item/preço/subtotal/peso/quote. Campo de quantidade
é apenas draft visual, sem alterar os valores recebidos. Após sucesso, somente Cart recebido e
validado substitui cache. Erro faz refetch de cart e invalida consultas de produto/catálogo; se a
reconciliação também falha, erro de query bloqueia edição sem fabricar dados atuais. Mutation não tem retry.
Produto no catálogo pode reprecificar: o valor efetivo mostrado no carrinho é o receipt do backend.

Somente GET de carrinho em falha de rede transitória tem um retry de leitura (100 ms), sem retry de
erros HTTP/protocolo ou de POST/PATCH/DELETE. Uma alteração do servidor pode mudar revisão e reinicializa o draft de linha. Carrinho inexistente/
encerrado tem reset explícito da **referência local**, não DELETE de banco nem criação automática.
Backend só reserva estoque na confirmação de pedido futura; todos os writes de carrinho permanecem sem reserva.

## Tipagem e autoridade comercial

Zod valida Product/Page/Cart/Item e UUIDs, inteiros seguros, flags e totais. Checagem de igualdade
das somas/linhas serve apenas para **rejeitar resposta incoerente**, não substituir preço por cálculo
do navegador. Totais exibidos são o subtotal/peso retornados. Money formatter apenas apresenta BRL.
Payload de mutation é reconstruído com campos permitidos (ID/quantidade/revisão); nunca serializa
objeto Product/Cart inteiro como autoridade comercial. Cents/peso/IDs de tenant extras são recusados.

Cliente interno normaliza HTTP errors por allowlist de códigos próprios conhecidos (estoque/conflito),
sem imprimir message privada/SQL/URI do servidor. Sem Authorization, API key, chamada Packsenvios,
redirect/proxy externo no navegador. Refetch em conflito não implica aprovação automática de nova compra.

## Verificação

Vitest: dados de API explicitamente sintéticos em `src/test/store-server.ts`, não fallback runtime.
Jornada, busca/filtro/detalhe, esgotado, preço alterado pelo servidor, refetch de erro/conflict,
estado pendente sem total otimista e schemas de receipt/identidade são verificados.
Backend PostgreSQL verifica busca global/case-insensitive, filtro depois das reservas e paginação.

Teste adicional `test_store_browser.py` sobe Uvicorn/Vite com schema PostgreSQL próprio, executa
Edge headless por Playwright, sem interceptar as APIs comerciais: adiciona 2 livros, atualiza 3,
confere R$91,80 → R$137,70 e 0,9 → 1,35 kg, recarrega a referência persistida e remove todos os itens.
Asserts do banco confirmam CartItem vazio e Inventory.reserved intacto. Servers/browser são encerrados.
Screenshot mobile é salvo em tmp_path do teste, não no banco/ambiente do usuário. Nenhum schema public
ou ambiente externo é migrado; tests só aceitam loopback e prefixo de schema próprio.

## Resultados efetivamente executados

Execução: 09/10/2026. Dependências existentes atenderam à feature; não foram necessários pacotes
adicionais ou migration. Marker browser adicionado ao pytest para evidência explícita.

| Comando / verificação | Resultado efetivo |
|---|---|
| `dev.ps1 Format` / Ruff / Prettier | PASS na rodada final |
| `dev.ps1 Check` | **235 PASS backend**, sem SKIP ou warnings na rodada final |
| Busca/filtro backend novos, incluídos acima | **2 PASS** em PostgreSQL real |
| Navegador/API/DB real, incluído acima | **1 PASS**, Edge mobile 390px, sem interceptar APIs comerciais |
| Regressão backend incluída acima | **232 PASS** |
| Vitest/Testing Library | **28 PASS** (8 jornada de loja + 2 validações store + 18 base anteriores) |
| ESLint / TypeScript / Vite build | PASS |
| `dev.ps1 LayoutCheck` | **5 PASS**, 320/390/768/1280 e keyboard |
| `dev.ps1 Smoke` | PASS; backend/Vite e health/runtime por proxy |
| Matriz contratual | PASS; 14 rotas documentadas e 3 exemplos JSON válidos, sem HTTP Packsenvios |
| `docker compose config --quiet` | PASS; não comprova runtime Docker |
| `git diff --check` | PASS |
| Screenshot carrinho mobile com API real | Gerado e inspecionado no tmp_path do teste (3 livros, R$137,70 e 1,35kg) |
| Processos PostgreSQL próprios ao terminar | **0** |

Comandos da última rodada agregada, na raiz:

```powershell
$env:TEST_POSTGRES_BIN = 'C:\Users\jacks\AppData\Local\Temp\opencode\freight-domain-pg-20261008\pgsql\bin'
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\dev.ps1 Format
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\dev.ps1 Check
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\dev.ps1 Smoke
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\dev.ps1 LayoutCheck
```

O teste live foi também executado individualmente com `pytest tests/test_store_browser.py`.
Usou PostgreSQL portátil 17.6 em schema aleatório próprio, Uvicorn/Vite nas portas loopback livres
e Edge já instalado. O Node verificou que cada write só levou campos permitidos, sem Authorization,
recarregou o carrinho antes de atualizar e não fez requisição fora de 127.0.0.1. O banco confirmou
CartItem vazio ao fim e Inventory.reserved igual a zero. Servidores/browser/cluster foram encerrados.

### Correções e falhas intermediárias

- Primeira rodada Vitest passou, mas TypeScript detectou `exact` não suportado nas opções ByRole
  Testing Library e ESLint globais browser dentro de page.evaluate no script Node. Corrigidos
  sem desabilitar checagem de tipos ou regras; build/lint subsequentemente passaram.
- Uma execução individual posterior do teste live falhou por leitura transitória de rede antes
  de enviar PATCH (UI mostrou erro seguro; não houve escrita duplicada). Diagnóstico de requestfailed
  adicionado, e somente GET de carrinho recebeu um retry limitado. Nenhuma mutação é reexecutada.
  Caso unitário de leitura transitória foi adicionado; execuções individual/agregada finais passaram.
- Caminhos de tmp de pytest em PYTEST_ADDOPTS foram passados com barras `/` na rodada final para
  evitar interpretação de backslash no parsing da variável. Screenshot final foi localizado e lido
  em `C:\Users\jacks\AppData\Local\Temp\opencode\freight-store-complete\...`.
- Uma aplicação de patch sem contexto correspondente foi reaplicada após leitura; nenhum dado
  de usuário foi sobrescrito. Nenhum commit/push foi executado.

## Limitações e próximo prompt

- Popule o PostgreSQL **local** configurado com Migrate/Seed para usar o catálogo do ambiente.
  Tests usaram somente schemas próprios; não alteraram public nem ambiente externo.
- Não foi feita chamada Packsenvios real, cotação/seleção externa, contratação ou pagamento.
  Browser não recebe Bearer; filtros/endpoints adicionados são contratos internos da loja.
- Checkout/endereços/cotação visual e finalização permanecem nos prompts posteriores. Esta etapa
  completa a escolha de produtos e edição do carrinho, não compra/contratação real.
- Runtime Docker não foi executado; persistência foi provada por PostgreSQL portátil real.
  Teste browser real é SKIP explícito fora de ambientes com Node/dependências/Edge/DB local disponíveis.

**Próximo prompt desbloqueado: 10 — Checkout e comparação de fretes.**
