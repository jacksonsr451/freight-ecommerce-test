import { ApiError } from '../api/http';
import { useHealth, useRuntime } from '../lib/runtime-queries';
import { Button, ErrorState, LoadingState, PageHeading } from '../components/ui';

export default function DiagnosticsPage() {
  const health = useHealth();
  const runtime = useRuntime();
  const refresh = () => {
    void Promise.all([health.refetch(), runtime.refetch()]);
  };
  const error = health.error ?? runtime.error;

  return (
    <>
      <PageHeading eyebrow="Transparência do ambiente" title="Diagnóstico local">
        Confira a aplicação da loja e o modo configurado. Nenhuma credencial é exibida.
      </PageHeading>
      <div className="diagnostic-toolbar">
        <span className="subtle-badge">API interna da loja</span>
        <Button
          className="button-secondary"
          disabled={health.isFetching || runtime.isFetching}
          onClick={refresh}
        >
          {health.isFetching || runtime.isFetching ? 'Atualizando…' : 'Atualizar diagnóstico'}
        </Button>
      </div>
      {health.isPending || runtime.isPending ? (
        <LoadingState label="Verificando a API e o modo de cotação…" />
      ) : error ? (
        <ErrorState
          message={
            error instanceof ApiError
              ? error.message
              : 'Não foi possível verificar o ambiente local.'
          }
          onRetry={refresh}
        />
      ) : (
        <div className="diagnostic-grid">
          <section className="surface-card">
            <span className="status-pill">Conectada</span>
            <h2>Aplicação local</h2>
            <dl>
              <dt>Serviço</dt>
              <dd>{health.data?.service}</dd>
              <dt>Última leitura</dt>
              <dd>{new Date(health.dataUpdatedAt).toLocaleTimeString('pt-BR')}</dd>
            </dl>
          </section>
          <section className="surface-card">
            <span className="status-pill neutral">
              {runtime.data?.freight_mode === 'mock' ? 'Mock' : 'Real'}
            </span>
            <h2>Modo de cotação</h2>
            <p>
              {runtime.data?.freight_mode === 'mock'
                ? 'Transport sintético, sem chamadas à rede de fretes.'
                : 'Adapter real configurado no backend. Isso não comprova disponibilidade externa.'}
            </p>
            <p>Compras e pagamentos permanecem locais e simulados.</p>
          </section>
        </div>
      )}
      <div className="notice">
        <strong>O que esta leitura confirma?</strong>
        <p>
          O processo da API local e sua configuração pública mínima. Não confirma PostgreSQL,
          transportadoras, filas ou homologação Packsenvios.
        </p>
      </div>
    </>
  );
}
