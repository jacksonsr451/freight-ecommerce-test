# Infraestrutura de desenvolvimento

`docker-compose.yml` na raiz define PostgreSQL 17.11 com volume persistente,
backend FastAPI e frontend Vite, com healthchecks e portas expostas apenas em loopback.
Dockerfiles usam os lockfiles do projeto e não copiam `.env` ou dependências do host.
Os processos de aplicação/teste rodam como usuários não-root dentro dos containers. O Dockerfile de
runtime instala somente o grupo Poetry `main`; `backend-test.Dockerfile` instala também `dev` e é usado
apenas pelo perfil Compose `test`. As imagens incluem `LICENSE` e `THIRD_PARTY_NOTICES.md`.

O modelo de domínio possui SQLAlchemy, psycopg e migration Alembic inicial (prompt 03).
Migrations são explícitas, não executadas no startup. O healthcheck é liveness da aplicação,
não valida conexão ou estado de migrations do banco.
`docker compose config --quiet` valida configuração; não comprova build ou inicialização de containers.
Execute a suíte Python isolada (inclui PostgreSQL e remove recursos temporários) por
`python scripts/dev.py compose-test`.
