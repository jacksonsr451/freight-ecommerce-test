# Segurança

A política oficial do repositório está em [`../../SECURITY.md`](../../SECURITY.md). Este guia resume os
limites efetivos e as pendências atuais.

## Dados e credenciais

- `.env` é local/ignorado; `.env.example` contém credenciais sintéticas de desenvolvimento e campos
  externos vazios.
- `FREIGHT_API_KEY`, segredo HMAC e URLs/credenciais de banco nunca devem ser expostos em frontend,
  logs, dumps, screenshots ou diagnósticos públicos.
- Testes de persistência precisam de database local separado e criam somente schemas de teste próprios.
- Testes do repo usam endereços, IDs, bearer e documentos sintéticos; não acrescente dados reais.

## Fronteiras efetivas

- `X-Local-Admin-Key` é uma barreira de administração local em development/test e desabilitada em
  production; não substitui autenticação/autorização de produção.
- Packsenvios é acessado pelo backend; o browser não envia Bearer. `FREIGHT_MODE=real` só indica
  configuração, não autorização/homologação.
- Compose publica portas no loopback do host. O backend container escuta na rede Compose para ser
  alcançado pelos containers pares.
- Não há middleware CORS permissivo; desenvolvimento browser usa proxy same-origin.

## Auditorias

`npm audit --audit-level=high` foi executado durante esta auditoria e retornou zero vulnerabilidades
conhecidas. `pip-audit` 2.10.1 não encontrou vulnerabilidades conhecidas nas dependências Python de
terceiros instaladas; informou que o pacote local não foi auditado porque não está publicado no PyPI.
O workflow também audita o virtualenv Poetry, e a dependency review action roda em pull requests.
Esses scanners não substituem revisão de código, verificação de licença ou homologação do provedor.

Canal privado de vulnerabilidades e contato privado do Code of Conduct ainda precisam ser configurados
nas settings do GitHub; detalhes e instruções sem canal inventado estão em `SECURITY.md` e
`CODE_OF_CONDUCT.md`.
