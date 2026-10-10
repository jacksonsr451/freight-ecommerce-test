import { useQuery } from '@tanstack/react-query';
import { ApiError } from '../api/http';
import { exportDiagnosticReport, getDiagnostics } from '../api/diagnostics';
import { useHealth, useRuntime } from '../lib/runtime-queries';
import { Button, ErrorState, LoadingState, PageHeading } from '../components/ui';

function statusLabel(status: string) {
  return (
    {
      ok: 'OK',
      configured: 'Configurado',
      unavailable: 'Indisponível',
      not_configured: 'Não configurado',
      not_checked: 'Não verificado',
    }[status] ?? status
  );
}

function formatJson(value: unknown) {
  return JSON.stringify(value, null, 2);
}

export default function DiagnosticsPage() {
  const health = useHealth();
  const runtime = useRuntime();
  const report = useQuery({
    queryKey: ['diagnostic-report'],
    retry: false,
    queryFn: ({ signal }) => getDiagnostics(signal),
  });
  const refresh = () => {
    void Promise.all([health.refetch(), runtime.refetch(), report.refetch()]);
  };
  const error = report.error ?? health.error ?? runtime.error;
  const busy = health.isFetching || runtime.isFetching || report.isFetching;

  return (
    <>
      <PageHeading eyebrow="Observabilidade segura" title="Diagnóstico local">
        Modo, saúde local e etapas da integração por correlação. O diagnóstico não consulta a API
        externa e não exibe credenciais, documentos ou corpos completos.
      </PageHeading>
      <div className="diagnostic-toolbar">
        <span className="subtle-badge">API interna da loja</span>
        <Button className="button-secondary" disabled={busy} onClick={refresh}>
          {busy ? 'Atualizando…' : 'Atualizar diagnóstico'}
        </Button>
        <Button
          className="button-secondary"
          disabled={!report.data || report.isFetching}
          onClick={() => report.data && exportDiagnosticReport(report.data)}
        >
          Exportar relatório redigido
        </Button>
      </div>
      {health.isPending || runtime.isPending || report.isPending ? (
        <LoadingState label="Verificando a API, banco local e auditoria…" />
      ) : error ? (
        <ErrorState
          message={
            error instanceof ApiError
              ? error.message
              : 'Não foi possível verificar o ambiente local.'
          }
          onRetry={refresh}
        />
      ) : report.data ? (
        <>
          <div className="diagnostic-grid">
            <section className="surface-card">
              <span className={`status-pill ${health.isSuccess ? '' : 'neutral'}`}>
                {health.isSuccess ? 'Conectada' : 'Indisponível'}
              </span>
              <h2>API da loja</h2>
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
              <h2>Compra local</h2>
              <p>Cotação: {runtime.data?.freight_mode}. Compras e pagamentos sempre simulados.</p>
              <p>Modo real configurado não comprova disponibilidade nem homologação externa.</p>
            </section>
            {report.data.checks.map((check) => (
              <section className="surface-card diagnostic-check" key={check.name}>
                <span
                  className={`status-pill ${check.status === 'ok' || check.status === 'configured' ? '' : 'neutral'}`}
                >
                  {statusLabel(check.status)}
                </span>
                <h2>{check.name}</h2>
                {check.latency_ms !== null && check.latency_ms !== undefined && (
                  <p>Latência local: {check.latency_ms} ms</p>
                )}
                <pre>{formatJson(check.details)}</pre>
              </section>
            ))}
          </div>

          <section className="surface-card diagnostic-summary">
            <h2>Fluxos pendentes</h2>
            <dl>
              <dt>Lotes de importação pendentes</dt>
              <dd>{report.data.pending_import_batches ?? 'Indisponível'}</dd>
              <dt>Webhooks aguardando reconciliação</dt>
              <dd>{report.data.pending_webhook_receipts ?? 'Indisponível'}</dd>
              <dt>Verificação externa</dt>
              <dd>Não executada por esta tela</dd>
            </dl>
          </section>

          <section className="surface-card diagnostic-operations">
            <div className="card-heading">
              <h2>Etapas e auditoria recente</h2>
              <span>{report.data.operations.length} registros</span>
            </div>
            {report.data.operations.length === 0 ? (
              <p>Nenhuma chamada auditada ainda.</p>
            ) : (
              <ol>
                {report.data.operations.map((operation) => (
                  <li key={operation.correlation_id}>
                    <div className="diagnostic-operation-heading">
                      <strong>{operation.operation}</strong>
                      <span
                        className={`status-pill ${operation.outcome === 'succeeded' ? '' : 'neutral'}`}
                      >
                        {operation.outcome}
                      </span>
                    </div>
                    <dl>
                      <dt>Correlação</dt>
                      <dd>{operation.correlation_id}</dd>
                      <dt>Modo / HTTP</dt>
                      <dd>
                        {operation.mode} · {operation.http_status ?? 'sem resposta'}
                      </dd>
                      <dt>Latência</dt>
                      <dd>{operation.latency_ms === null ? '—' : `${operation.latency_ms} ms`}</dd>
                      {operation.error_code && (
                        <>
                          <dt>Erro normalizado</dt>
                          <dd>{operation.error_code}</dd>
                        </>
                      )}
                      {operation.retry_after_seconds !== null && (
                        <>
                          <dt>Retry-After</dt>
                          <dd>{operation.retry_after_seconds} s</dd>
                        </>
                      )}
                      {operation.request_key && (
                        <>
                          <dt>request_key</dt>
                          <dd>{operation.request_key}</dd>
                        </>
                      )}
                      {operation.external_quote_id && (
                        <>
                          <dt>Quote ID externo</dt>
                          <dd>{operation.external_quote_id}</dd>
                        </>
                      )}
                      {operation.quote_id && (
                        <>
                          <dt>Quote ID local</dt>
                          <dd>{operation.quote_id}</dd>
                        </>
                      )}
                      {operation.import_batch_id && (
                        <>
                          <dt>Lote local</dt>
                          <dd>{operation.import_batch_id}</dd>
                        </>
                      )}
                    </dl>
                    {Object.keys(operation.redacted_details).length > 0 && (
                      <details>
                        <summary>Detalhes allowlistados</summary>
                        <pre>{formatJson(operation.redacted_details)}</pre>
                      </details>
                    )}
                    {operation.snapshot_summary && (
                      <details>
                        <summary>Resumo de snapshot (valores redigidos)</summary>
                        <pre>{formatJson(operation.snapshot_summary)}</pre>
                      </details>
                    )}
                  </li>
                ))}
              </ol>
            )}
          </section>
          <div className="notice">
            <strong>Sem segredos nem dados fiscais.</strong>
            <p>
              O relatório contém IDs operacionais e campos allowlistados; não inclui Bearer, chave
              de assinatura, request/response body, endereço, CPF/CNPJ, e-mail ou etiquetas.
            </p>
          </div>
        </>
      ) : null}
    </>
  );
}
