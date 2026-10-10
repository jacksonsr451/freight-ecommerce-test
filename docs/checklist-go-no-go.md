# Checklist GO / NO-GO — entrega 18

Regra: `PASS` somente após comando/runner realmente executar. `SKIP`/`PENDING` não equivale a PASS.
As credenciais reais permanecem fora do relatório.

## Estado desta revisão

| Gate | Windows 10/11 | Linux | Evidência / decisão |
|---|---|---|---|
| Root/manifests identificados | PASS | PASS (inspeção) | Poetry apenas em `backend/`; npm apenas em `frontend/`; root pelo script relativo ao próprio arquivo |
| Python cross-platform CLI / wrapper | PASS (`dev.py`, PowerShell wrapper) | PASS (`dev.py`, Bash wrapper/doctor) | `doctor` detectou ferramentas e daemon conforme cada sistema |
| Setup e validação `.env` | PASS | PENDING | Windows executou `setup` + `env-check`; Linux setup aguarda Poetry/Node Linux |
| Backend, PostgreSQL, migrations/seed | PASS | PENDING | Windows `check`: 280 testes; Linux Poetry/Python host checks ainda não executados |
| Frontend/typecheck/lint/build | PASS | PENDING | Windows `check`: 54 testes e build; Linux Node host não instalado |
| Playwright jornada local | PASS (Edge/Windows, layout 5/5) | PENDING | Chromium Linux configurado no CI; runner Linux ainda não executado |
| Docker Compose config | PASS | PASS | `compose-check`/`config --quiet` passou em Windows e WSL2 |
| Docker Compose build/up/health/down | PASS | PASS (WSL2) | `up`/healthchecks Windows e projetos efêmeros `compose-smoke` passaram em Windows e WSL2; smoke remove recursos próprios |
| HTTP Packsenvios, jobs, despacho, webhook externo | SKIP | SKIP | Nenhuma credencial/entrega/homologação real foi exercitada |
| Exportação do modelo oficial | NO-GO | NO-GO | TODO-IMPORT-TEMPLATE: obter instrução linha 1 e 28 cabeçalhos oficiais exatos; export fica desabilitado |
| Receiver de webhook homologado | NO-GO | NO-GO | Timestamp header sem unidade no guia; confirmar formato e destino público HTTPS/443 antes de configurar |

## Decisão de entrega

- **GO para demonstração local/mock em Windows**: setup, check (280 backend + 54 frontend), smoke,
  layout e Compose startup passaram. **GO para Compose Linux via WSL2**: build, healthchecks e proxy
  passaram; suíte Linux de host permanece pendente. Compra/pagamento/pedido permanecem simulados.
- **NO-GO para homologação externa** até concluir pré-requisitos de `docs/homologacao.md`, repetir
  testes reais autorizados e separar evidência de API, filas, aceite e entrega.
- Não remover `manual_only`, limites de confirmação/importação, bloqueios de retry incerto ou redaction
  para tentar tornar o gate verde.
