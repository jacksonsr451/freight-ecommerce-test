# ADR 0001: demonstração local e fronteiras do provedor

- **Status:** Accepted (as implemented)
- **Context:** o repositório demonstra um fluxo local de e-commerce com adapters Packsenvios
  condicionados a contrato e configuração autorizada.
- **Decision:** persistência e regras comerciais ficam no backend FastAPI/PostgreSQL; o browser chama
  somente a API local. Frete mock é sintético. Compra e pagamento permanecem simulados. Segredos de
  provedor são server-only. Valores `manual_only` são apenas vínculo local e nunca autorizam contratação
  automática.
- **Consequences:** teste local pode provar estado local e fixtures, mas não confirma acesso, cotação
  externa, importação aceita, despacho, etiqueta, tracking, entrega ou homologação. Um modo real
  configurado não muda essa interpretação. Ambiguidade contratual bloqueia a feature externa até
  evidência/decisão autorizada.
- **Source:** `docs/reference/gestao-frete-integracao-ecommerce-teste.md` e módulos implementados em
  `backend/src/freight_ecommerce/`.
