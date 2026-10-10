# 04 — API local de catálogo e estoque

> **Registro histórico pré-prompt 19:** comandos pytest abaixo documentam a rodada original; a suíte
> atual usa jsr-testrunner. Veja `docs/development-testing.md`.

Raiz: `E:\Softwares\joao\tests`. Reutiliza Product/Inventory e a migration 0001;
nenhuma nova tabela, migration ou integração Packsenvios foi necessária.

## Contrato interno

Todos os caminhos desta seção são da **loja local**, não endpoints Packsenvios.
OpenAPI gerado em `/openapi.json` e Swagger `/docs`; schemas em `catalog/schemas.py`.

| Operação | Resposta / regras |
|---|---|
| GET `/api/products` | `{items,total,page,page_size,total_pages}`. Página >=1; tamanho 1–100; ordem SKU/UUID; somente ativos com inventário |
| GET `/api/products/{product_id}` | ProductView; 404 para inexistente/inativo; 422 para UUID inválido |
| POST `/api/products/{product_id}/stock-check` | Quantity somente (inteiro 1–1000); preço unitário, subtotal e peso total derivados do cadastro; 409 se disponibilidade insuficiente |
| GET `/api/admin/products` | Paginação incluindo inativos; AdminProductView com inventário/reservas/versão e timestamps |
| GET `/api/admin/products/{product_id}` | Detalhe administrativo, inclui inativo |
| POST `/api/admin/products` | 201 com produto/inventário criados em transação única |
| PATCH `/api/admin/products/{product_id}` | 200; patch não vazio/não nulo; bloqueia estoque abaixo das reservas; SKU único |
| DELETE `/api/admin/products/{product_id}` | 204 sem corpo; desativa, não remove fisicamente; repetição idempotente |

ProductView contém UUID, SKU, nome, preço centavos, peso gramas, três dimensões cm,
disponibilidade e status `active|inactive`. Admin adiciona estoque físico/reservado/disponível,
versão e datas UTC. Nenhuma credencial, dado de cliente ou documento fiscal é retornado.
ProductCreate/Patch recusam campos extras (inclusive `reserved` e IDs arbitrários).
Valores numéricos são inteiros estritos: floats, strings numéricas e booleanos são recusados.

Limites **locais de entrada do catálogo demonstrativo**: preço 0–100.000.000 centavos,
peso 1–50.000.000 g, dimensões 1–300 cm, estoque 0–2.147.483.647, SKU até 64 e nome até 160.
Não constituem cotação/contratação nem ampliam permissões ou limites externos.
O SKU é normalizado (trim/uppercase) e deve conter letras ASCII, números, ponto, hífen ou underscore.
Patch omite campos que não mudam; null explícito é rejeitado também no OpenAPI gerado.

## Restrição administrativa

- Header de operador local `X-Local-Admin-Key`, independente de Bearer Packsenvios.
- `LOCAL_ADMIN_KEY` em SecretStr server-only, sem valor fixo habilitado por padrão.
- Vazio / produção: 403 `local_admin_disabled`; ausente/incorreto quando habilitado: 401.
- Comparação em tempo constante. Não existe autorização para operações externas derivada dessa chave.
- Este é controle de desenvolvimento local, não autenticação administrativa definitiva de produção.
- Autorização roda antes de consultar banco; testes de recusa não precisam de PostgreSQL disponível.

## Integridade e autoridade do servidor

- CRUD monta explicitamente Product/Inventory a partir de schemas permitidos; criação atomicamente
  persistida, sem produto órfão se o inventário falhar.
- UPDATE/DELETE bloqueiam linhas Product/Inventory com `FOR UPDATE`; Inventory conserva
  versionamento otimista e checks já existentes. `stock_on_hand < reserved` retorna 409.
- DELETE lógico preserva histórico e FKs. Reativação depende de PATCH administrativo explícito.
- Publicação exige produto ativo e inventário; esgotado permanece visível com estoque zero.
- `stock-check` só lê disponibilidade; não garante estoque futuro nem cria reserva, carrinho ou pedido.
- Subtotal usa preço armazenado no banco, peso usa cadastro; preço enviado pelo cliente é rejeitado.
- Conflitos persistidos/concorrência retornam 409 normalizado, falha operacional de banco 503.
  Erros internos SQL/URI/credenciais não são devolvidos ao cliente.
- Serviços 05/11 ainda deverão recalcular e revalidar na confirmação do pedido.

## Seeds e execução

`catalog/seed.py` disponibiliza sete produtos **sintéticos**: livro, caneca, mochila, fone,
luminária, esgotado e inativo. UUIDs determinísticos; SKU identifica registros existentes.
Reexecução preserva valores/estoque/status alterados. Nenhum seed roda automaticamente.
O CLI recusa produção e bancos remotos; testes utilizam apenas schemas próprios em loopback.

```powershell
# Após Migrate em PostgreSQL local:
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\dev.ps1 Seed
# Verificação completa com PostgreSQL real (ou configure TEST_DATABASE_URL loopback):
$env:TEST_POSTGRES_BIN = 'C:\Users\jacks\AppData\Local\Temp\opencode\freight-domain-pg-20261008\pgsql\bin'
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\dev.ps1 Check
```

## Evidências

Data: 08/10/2026. Não foi necessário instalar dependências adicionais: FastAPI/Pydantic,
SQLAlchemy/psycopg, pytest/AnyIO e HTTPX existentes suportam a feature. Lockfile permaneceu válido.

| Comando / verificação | Resultado efetivo |
|---|---|
| `poetry run ruff format .` / `poetry run ruff check .` | PASS na rodada final |
| `poetry check --lock` | PASS |
| `pytest tests/test_catalog_auth.py tests/test_smoke.py -q` (rodada inicial) | 8 PASS, sem banco |
| `pytest tests/test_catalog_api.py ... -x -q` (rodada inicial) | 32 PASS com PostgreSQL real |
| `dev.ps1 Check` com `TEST_POSTGRES_BIN` | **85 PASS backend**, sem SKIP ou warnings na rodada final |
| Testes novos de API incluídos acima | **35 PASS**: paginação, detalhes, CRUD, centavos, inativos/esgotados, reservas, payloads, rollback e seeds |
| Testes novos de autorização/contrato incluídos acima | **9 PASS**: todas as rotas admin recusadas sem autoridade, produção/vazio bloqueados, OpenAPI, segredo oculto e seed local |
| Regressão de domínio/persistência/smoke incluída acima | **41 PASS**, incluindo reversibilidade e check Alembic sem drift |
| Vitest | **4 PASS** |
| ESLint / Prettier / TypeScript / Vite build | PASS |
| Validação contratual | PASS; 14 rotas Pack documentadas e 3 exemplos JSON válidos, sem executar essas rotas |
| `dev.ps1 Smoke` | PASS; FastAPI/Vite/proxy inicializados e encerrados localmente |
| `docker compose config --quiet` | PASS |
| `git diff --check` | PASS; apenas aviso Git de normalização LF/CRLF do script PowerShell |
| Conferência de processos PostgreSQL próprios após os testes | **0** |

Os 61 testes marcados PostgreSQL (35 de catálogo e 26 de persistência) rodaram com PostgreSQL
17.6 **real**, usando o bundle portátil já disponível no diretório temporário aprovado. A fixture
iniciou/encerrou um cluster próprio e cada teste criou/removeu apenas seu schema aleatório.
O entrypoint do seed também foi executado contra schema próprio: 7 criados, reexecução preservou os 7.
Nenhum catálogo de banco externo, public ou ambiente compartilhado foi populado pelo agente.

Pequenos problemas iniciais de docstring longa e ordenação de imports apontados pelo Ruff foram
corrigidos antes da verificação completa. Nenhum teste falhou na rodada final.

## Limitações e próximo prompt

- Docker continuou inacessível pelo pipe `dockerDesktopLinuxEngine`; runtime/build Docker não
  foram revalidados. Isso não substitui nem invalida a execução dos testes em PostgreSQL real local.
- Usar `Migrate` e `Seed` no banco local configurado antes de consultar o catálogo do ambiente de
  desenvolvimento; os dados dos testes foram deliberadamente isolados e descartados.
- Stock-check é validação momentânea, sem reserva. Concorrência de compra/reserva definitiva pertence
  aos serviços dos prompts 05/11; CRUD mantém locks/checks existentes.
- Sem integração HTTP Packsenvios, Bearer no navegador, pagamento real ou comportamento externo fabricado.
- Frontend de catálogo não é parte desta feature (previsto no prompt 09); a API foi validada via HTTPX/ASGI.

**Próximo prompt desbloqueado: 05 — Carrinho e cálculo comercial.**
