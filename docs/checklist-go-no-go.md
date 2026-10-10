# Checklist GO / NO-GO — entrega 18

Regra: `PASS` somente após comando/runner realmente executar. `SKIP`/`PENDING` não equivale a PASS.
As credenciais reais permanecem fora do relatório.

## Estado desta revisão

| Gate | Windows 10/11 | Linux | Evidência / decisão |
|---|---|---|---|
| Root/manifests identificados | PASS | PASS (inspeção) | Poetry apenas em `backend/`; npm apenas em `frontend/`; root pelo script relativo ao próprio arquivo |
| Python cross-platform CLI / wrapper | PENDING | PENDING | Repetir `python scripts/dev.py doctor`, `scripts/dev.ps1` no Windows e `bash scripts/dev.sh` no Linux após executar os wrappers |
| Setup e validação `.env` | PENDING | PENDING | `python scripts/dev.py setup` e `env-check`; `.env` só é copiado quando ausente |
| Backend, PostgreSQL, migrations/seed | PASS (suíte local já executada em Windows) | PENDING | Suíte cria/removе schemas efêmeros; executar CI Linux para registrar a matriz final |
| Frontend/typecheck/lint/build | PASS (suíte local já executada em Windows) | PENDING | npm Node 24/npm 11; runner Linux ainda não executado neste workspace |
| Playwright jornada local | PASS (Edge/Windows) | PENDING | Chromium Linux configurado no CI; precisa do resultado do runner Linux |
| Docker Compose config | PASS | PASS (config inspecurada no runner WSL) | Não implica build/startup |
| Docker Compose build/up/health/down | PENDING | PENDING | Executar `python scripts/dev.py compose-smoke` em ambos os runners; cleanup usa projeto/volume temporário próprios |
| HTTP Packsenvios, jobs, despacho, webhook externo | SKIP | SKIP | Nenhuma credencial/entrega/homologação real foi exercitada |
| Exportação do modelo oficial | NO-GO | NO-GO | TODO-IMPORT-TEMPLATE: obter instrução linha 1 e 28 cabeçalhos oficiais exatos; export fica desabilitado |
| Receiver de webhook homologado | NO-GO | NO-GO | Timestamp header sem unidade no guia; confirmar formato e destino público HTTPS/443 antes de configurar |

## Decisão de entrega

- **GO para demonstração local/mock** quando `setup`, `check`, `smoke`, layout e Compose startup
  passarem no sistema alvo. Compra/pagamento/pedido permanecem locais e simulados.
- **NO-GO para homologação externa** até concluir pré-requisitos de `docs/homologacao.md`, repetir
  testes reais autorizados e separar evidência de API, filas, aceite e entrega.
- Não remover `manual_only`, limites de confirmação/importação, bloqueios de retry incerto ou redaction
  para tentar tornar o gate verde.
