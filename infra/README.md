# Infraestrutura de desenvolvimento

`docker-compose.yml` na raiz define PostgreSQL 17 com volume persistente,
backend FastAPI e frontend Vite, com healthchecks e portas expostas apenas em loopback.
Dockerfiles usam os lockfiles do projeto e não copiam `.env` ou dependências do host.

O banco está provisionado no Compose, mas o bootstrap ainda não possui camada de persistência,
driver PostgreSQL, Alembic ou migrations. O healthcheck da aplicação é liveness local.
`docker compose config --quiet` valida configuração; não comprova build ou inicialização de containers.
