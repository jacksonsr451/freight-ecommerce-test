# Infraestrutura de desenvolvimento

`docker-compose.yml` na raiz define PostgreSQL 17 com volume persistente,
backend FastAPI e frontend Vite, com healthchecks e portas expostas apenas em loopback.
Dockerfiles usam os lockfiles do projeto e não copiam `.env` ou dependências do host.

O modelo de domínio possui SQLAlchemy, psycopg e migration Alembic inicial (prompt 03).
Migrations são explícitas, não executadas no startup. O healthcheck é liveness da aplicação,
não valida conexão ou estado de migrations do banco.
`docker compose config --quiet` valida configuração; não comprova build ou inicialização de containers.
