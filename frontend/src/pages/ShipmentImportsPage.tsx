import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { ApiError } from '../api/http';
import {
  confirmImportBatch,
  dispatchImportBatch,
  getImportAvailability,
  getImportBatch,
  getImportExportReadiness,
  getImportTracking,
  listImportBatches,
  refreshImportTracking,
  uploadImportFile,
} from '../api/imports';
import { Button, EmptyState, PageHeading } from '../components/ui';

function message(error: unknown) {
  if (!(error instanceof ApiError)) return 'A API local de importação não está disponível.';
  if (error.retryAfterSeconds !== undefined)
    return `${error.message} Aguarde ${error.retryAfterSeconds} segundos antes de tentar novamente.`;
  return error.message;
}

function display(value: unknown) {
  if (value === null || value === undefined) return '—';
  if (typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean')
    return String(value);
  return JSON.stringify(value);
}

export default function ShipmentImportsPage() {
  const [key, setKey] = useState('');
  const [authSession, setAuthSession] = useState(0);
  const [selectedBatch, setSelectedBatch] = useState('');
  const [cursor, setCursor] = useState(0);
  const [errorsOnly, setErrorsOnly] = useState(false);
  const [operatorReviewed, setOperatorReviewed] = useState(false);
  const [expectedPageCursors, setExpectedPageCursors] = useState<number[]>([0]);
  const [reviewedPageCursors, setReviewedPageCursors] = useState<number[]>([]);
  const [trackingRow, setTrackingRow] = useState<number | null>(null);
  const [dispatchReviewed, setDispatchReviewed] = useState(false);
  const queryClient = useQueryClient();
  const enabled = key.trim().length >= 32;
  const availability = useQuery({
    queryKey: ['import-availability', authSession],
    enabled,
    retry: false,
    queryFn: ({ signal }) => getImportAvailability(key.trim(), signal),
  });
  const readiness = useQuery({
    queryKey: ['import-export-readiness', authSession],
    enabled,
    retry: false,
    queryFn: ({ signal }) => getImportExportReadiness(key.trim(), signal),
  });
  const batches = useQuery({
    queryKey: ['import-batches', authSession],
    enabled,
    retry: false,
    queryFn: ({ signal }) => listImportBatches(key.trim(), signal),
  });
  const detail = useQuery({
    queryKey: ['import-batch', authSession, selectedBatch, cursor, errorsOnly],
    enabled: enabled && Boolean(selectedBatch),
    retry: false,
    queryFn: ({ signal }) => getImportBatch(key.trim(), selectedBatch, cursor, errorsOnly, signal),
  });
  const tracking = useQuery({
    queryKey: ['import-tracking', authSession, selectedBatch, trackingRow],
    enabled: enabled && Boolean(selectedBatch) && trackingRow !== null,
    retry: false,
    queryFn: ({ signal }) => getImportTracking(key.trim(), selectedBatch, trackingRow!, signal),
  });
  const upload = useMutation({
    retry: false,
    mutationFn: (file: File) => uploadImportFile(key.trim(), file),
    onSuccess: async (batch) => {
      setSelectedBatch(batch.id);
      setCursor(0);
      setErrorsOnly(false);
      setOperatorReviewed(false);
      setExpectedPageCursors([0]);
      setReviewedPageCursors([]);
      await queryClient.invalidateQueries({ queryKey: ['import-batches', authSession] });
    },
  });
  const confirm = useMutation({
    retry: false,
    mutationFn: () => confirmImportBatch(key.trim(), selectedBatch),
    onSuccess: async () => {
      setOperatorReviewed(false);
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['import-batch', authSession, selectedBatch] }),
        queryClient.invalidateQueries({ queryKey: ['import-batches', authSession] }),
      ]);
    },
  });
  const dispatch = useMutation({
    retry: false,
    mutationFn: () => dispatchImportBatch(key.trim(), selectedBatch),
    onSuccess: async () => {
      setDispatchReviewed(false);
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['import-batch', authSession, selectedBatch] }),
        queryClient.invalidateQueries({ queryKey: ['import-batches', authSession] }),
      ]);
    },
  });
  const refreshTracking = useMutation({
    retry: false,
    mutationFn: (rowNumber: number) => refreshImportTracking(key.trim(), selectedBatch, rowNumber),
    onSuccess: async () => {
      await queryClient.invalidateQueries({
        queryKey: ['import-batch', authSession, selectedBatch],
      });
    },
  });
  const canReview = Boolean(
    detail.data &&
    ['review', 'confirming', 'imported'].includes(detail.data.external_status) &&
    detail.data.batch.valid > 0 &&
    !errorsOnly,
  );
  const canConfirm = Boolean(
    canReview &&
    !detail.data?.has_more &&
    operatorReviewed &&
    expectedPageCursors.every(
      (page) => reviewedPageCursors.includes(page) || (page === cursor && operatorReviewed),
    ),
  );
  const canDispatch = Boolean(
    detail.data &&
    availability.data?.dispatch_connection_configured &&
    detail.data.external_status === 'imported' &&
    detail.data.batch.total > 0 &&
    detail.data.batch.imported === detail.data.batch.total &&
    detail.data.batch.invalid === 0 &&
    detail.data.batch.processed >= detail.data.batch.total &&
    !detail.data.dispatch_retry_blocked &&
    detail.data.dispatch === null,
  );
  const markPageReviewed = (reviewed: boolean) => {
    setOperatorReviewed(reviewed);
    setReviewedPageCursors((pages) =>
      reviewed
        ? pages.includes(cursor)
          ? pages
          : [...pages, cursor]
        : pages.filter((page) => page !== cursor),
    );
  };

  return (
    <>
      <PageHeading eyebrow="Importação assistida" title="Preparar e acompanhar envios">
        Importar arquivo não cria pedido JSON nem altera os pedidos/pagamentos locais. O envio
        externo só é tentado em modo real, pelo backend, com credencial e empresa configuradas.
      </PageHeading>

      <section className="surface-card import-access">
        <label htmlFor="import-admin-key">Chave administrativa local</label>
        <input
          id="import-admin-key"
          type="password"
          autoComplete="off"
          value={key}
          onChange={(event) => {
            setKey(event.target.value);
            setAuthSession((session) => session + 1);
            setSelectedBatch('');
            setOperatorReviewed(false);
            setDispatchReviewed(false);
            setTrackingRow(null);
            setExpectedPageCursors([0]);
            setReviewedPageCursors([]);
          }}
          placeholder="Informe a chave local configurada no backend"
        />
        {enabled && availability.isSuccess && (
          <p role="status">
            Modo {availability.data.mode}.{' '}
            {availability.data.upload_enabled
              ? 'O backend pode tentar o gateway; a API validará abilities e titular.'
              : 'Upload desativado: configure modo real e empresa no backend.'}
          </p>
        )}
        {availability.isError && <p role="alert">{message(availability.error)}</p>}
      </section>

      {!enabled ? (
        <EmptyState title="Autenticação administrativa necessária">
          Informe a chave local autorizada. Nenhuma credencial Packsenvios é solicitada ao
          navegador.
        </EmptyState>
      ) : (
        <div className="import-workspace">
          <section className="surface-card import-preparation">
            <p className="eyebrow">Preparação local</p>
            <h2>Exportação oficial bloqueada</h2>
            <p>
              A referência descreve as 28 colunas semanticamente, mas não inclui o texto literal da
              instrução da linha 1 nem a grafia exata dos cabeçalhos da linha 2. Pedidos locais
              também não contêm todos os dados fiscais/remetente. Para não produzir um modelo
              incompatível, obtenha e preencha o arquivo atual em Meus Envios → Importação no portal
              autorizado.
            </p>
            {readiness.data && (
              <ul>
                {readiness.data.missing_fields.map((field) => (
                  <li key={field}>{field.replaceAll('_', ' ')}</li>
                ))}
              </ul>
            )}
            <Button disabled aria-disabled="true">
              Exportação não disponível
            </Button>
          </section>

          <section className="surface-card import-upload">
            <p className="eyebrow">Gateway opcional · somente real</p>
            <h2>Enviar arquivo oficial preenchido</h2>
            <p>
              Aceita CSV/XLSX, instrução na linha 1, cabeçalho na linha 2 e dados desde a linha 3.
              Limite: 29.296 KiB e 200.000 envios. Importação pode ficar pendente por processamento
              assíncrono.
            </p>
            <label htmlFor="shipment-import-file">Arquivo CSV ou XLSX do modelo atual</label>
            <input
              id="shipment-import-file"
              type="file"
              accept=".csv,text/csv,.xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
              disabled={!availability.data?.upload_enabled || upload.isPending}
              onChange={(event) => {
                const file = event.currentTarget.files?.[0];
                if (file) upload.mutate(file);
                event.currentTarget.value = '';
              }}
            />
            {upload.isPending && <p role="status">Enviando uma vez ao gateway real…</p>}
            {upload.isError && <p role="alert">{message(upload.error)}</p>}
            {upload.isSuccess && (
              <p role="status">
                Solicitação aceita pelo gateway. Lote {upload.data.id}; estado externo{' '}
                {upload.data.external_status ?? 'a consultar'}. Aceitação não significa importação
                concluída.
              </p>
            )}
          </section>

          <section className="surface-card import-batch-list">
            <h2>Lotes persistidos ({batches.data?.total ?? 0})</h2>
            {batches.isError && <p role="alert">{message(batches.error)}</p>}
            {batches.isPending ? <p role="status">Carregando lotes locais…</p> : null}
            {batches.data?.items.length === 0 && (
              <p>Nenhum lote local associado a esta configuração.</p>
            )}
            {batches.data?.items.map((batch) => (
              <button
                type="button"
                key={batch.id}
                className={`import-batch-row ${batch.id === selectedBatch ? 'selected' : ''}`}
                onClick={() => {
                  setSelectedBatch(batch.id);
                  setCursor(0);
                  setErrorsOnly(false);
                  setOperatorReviewed(false);
                  setDispatchReviewed(false);
                  setTrackingRow(null);
                  setExpectedPageCursors([0]);
                  setReviewedPageCursors([]);
                }}
              >
                <strong>{batch.filename}</strong>
                <span>Lote {batch.id}</span>
                <span>
                  Interno: {batch.local_status} · Externo: {batch.external_status ?? 'sem retorno'}
                </span>
                <span>
                  {batch.valid} válidas · {batch.invalid} rejeitadas · {batch.imported} importadas
                </span>
                <span>Despacho externo: {batch.dispatch_status ?? 'sem solicitação'}</span>
              </button>
            ))}
          </section>

          {selectedBatch && (
            <section className="surface-card import-batch-detail">
              <h2>Revisão do lote</h2>
              {detail.isPending && <p role="status">Consultando o estado do lote…</p>}
              {detail.isError && <p role="alert">{message(detail.error)}</p>}
              {detail.data && (
                <>
                  <dl className="import-summary-grid">
                    <dt>ID externo do lote</dt>
                    <dd>{detail.data.batch.id}</dd>
                    <dt>Arquivo</dt>
                    <dd>{detail.data.batch.filename}</dd>
                    <dt>Estado interno</dt>
                    <dd>{detail.data.batch.local_status}</dd>
                    <dt>Estado externo</dt>
                    <dd>{detail.data.external_status}</dd>
                    <dt>Despacho externo</dt>
                    <dd>{detail.data.batch.dispatch_status ?? 'sem solicitação externa'}</dd>
                    <dt>Linhas válidas</dt>
                    <dd>{detail.data.batch.valid}</dd>
                    <dt>Linhas rejeitadas</dt>
                    <dd>{detail.data.batch.invalid}</dd>
                    <dt>Importadas</dt>
                    <dd>{detail.data.batch.imported}</dd>
                    <dt>Processadas</dt>
                    <dd>{detail.data.batch.processed}</dd>
                  </dl>
                  {detail.data.issue !== null && (
                    <p className="notice">Ocorrência: {display(detail.data.issue)}</p>
                  )}
                  {detail.data.external_status === 'queued' ||
                  detail.data.external_status === 'parsing' ||
                  detail.data.external_status === 'confirming' ? (
                    <p role="status">
                      Fila assíncrona: aguardando processamento; consulte novamente para atualizar.
                    </p>
                  ) : null}
                  <div className="import-review-controls">
                    <label>
                      <input
                        type="checkbox"
                        checked={errorsOnly}
                        onChange={(event) => {
                          setErrorsOnly(event.target.checked);
                          setCursor(0);
                          setOperatorReviewed(false);
                          setExpectedPageCursors([0]);
                          setReviewedPageCursors([]);
                        }}
                      />
                      Mostrar somente linhas com inconsistências (errors_only=1)
                    </label>
                    <Button className="button-secondary" onClick={() => void detail.refetch()}>
                      Consultar lote agora
                    </Button>
                  </div>
                  <div className="import-rows">
                    {detail.data.items.map((row) => (
                      <article key={String(row.row)}>
                        <strong>
                          Linha {display(row.row)} · {display(row.status)}
                        </strong>
                        <span>
                          {display(row.recipientName)} · {display(row.destination)}
                        </span>
                        <span>
                          Envio externo: {display(row.shipmentId)} · {display(row.dispatchStatus)}
                        </span>
                        <pre>{JSON.stringify(row.errors ?? [], null, 2)}</pre>
                        <div className="import-row-actions">
                          <Button
                            className="button-secondary"
                            onClick={() => setTrackingRow(Number(row.row))}
                          >
                            Consultar snapshot real · linha {display(row.row)}
                          </Button>
                          <Button
                            className="button-secondary"
                            disabled={refreshTracking.isPending}
                            onClick={() => refreshTracking.mutate(Number(row.row))}
                          >
                            {refreshTracking.isPending
                              ? 'Solicitando…'
                              : `Solicitar atualização · linha ${display(row.row)}`}
                          </Button>
                        </div>
                        {trackingRow === Number(row.row) && (
                          <section
                            className="tracking-snapshot"
                            aria-label={`Snapshot real da linha ${display(row.row)}`}
                          >
                            <strong>Snapshot Packsenvios · linha {display(row.row)}</strong>
                            {tracking.isPending && <p role="status">Consultando snapshot…</p>}
                            {tracking.isError && <p role="alert">{message(tracking.error)}</p>}
                            {tracking.data && (
                              <>
                                <p>
                                  Capturado em{' '}
                                  {new Date(tracking.data.captured_at).toLocaleString('pt-BR')}.
                                  Etiquetas são dados de snapshot; não há download nesta tela.
                                </p>
                                <pre>{JSON.stringify(tracking.data.snapshot, null, 2)}</pre>
                              </>
                            )}
                          </section>
                        )}
                      </article>
                    ))}
                    {detail.data.items.length === 0 && <p>Nenhuma linha nesta página/filtro.</p>}
                  </div>
                  {detail.data.has_more && detail.data.next_cursor !== null && (
                    <Button
                      className="button-secondary"
                      disabled={!operatorReviewed}
                      onClick={() => {
                        setCursor(detail.data!.next_cursor!);
                        setExpectedPageCursors((pages) =>
                          pages.includes(detail.data!.next_cursor!)
                            ? pages
                            : [...pages, detail.data!.next_cursor!],
                        );
                        setOperatorReviewed(false);
                      }}
                    >
                      Carregar próxima página
                    </Button>
                  )}
                  {canReview && (
                    <div className="import-confirm-panel">
                      <label>
                        <input
                          type="checkbox"
                          checked={operatorReviewed}
                          onChange={(event) => markPageReviewed(event.target.checked)}
                        />
                        Revisei a página e as linhas exibidas; confirmo explicitamente somente as
                        linhas válidas.
                      </label>
                      {canConfirm && (
                        <Button disabled={confirm.isPending} onClick={() => confirm.mutate()}>
                          {confirm.isPending
                            ? 'Confirmando no gateway…'
                            : 'Confirmar linhas válidas'}
                        </Button>
                      )}
                      {detail.data.has_more && (
                        <p>Marque esta página como revisada para liberar a próxima página.</p>
                      )}
                      <p>Confirmação externa é assíncrona e não representa despacho.</p>
                    </div>
                  )}
                  {confirm.isError && <p role="alert">{message(confirm.error)}</p>}
                  {confirm.isSuccess && (
                    <p role="status">
                      Confirmação aceita; estado atual:{' '}
                      {confirm.data.external_status ?? confirm.data.local_status}. Consulte o lote
                      para ver processamento.
                    </p>
                  )}
                  {refreshTracking.isSuccess && (
                    <p role="status">
                      Atualização solicitada; status {refreshTracking.data.status}. O snapshot atual
                      não foi substituído até nova consulta.
                    </p>
                  )}
                  {refreshTracking.isError && <p role="alert">{message(refreshTracking.error)}</p>}
                  {!availability.data?.dispatch_connection_configured && (
                    <p className="notice">
                      Despacho indisponível: configure no backend uma conexão empresarial existente,
                      ativa, testada e homologada.
                    </p>
                  )}
                  {detail.data.dispatch_retry_blocked && (
                    <p className="notice">
                      Já existe uma solicitação de despacho ou resultado incerto. Não haverá novo
                      POST; consulte/reconcilie pelo fluxo autorizado existente.
                    </p>
                  )}
                  {canDispatch && (
                    <div className="import-confirm-panel">
                      <label>
                        <input
                          type="checkbox"
                          checked={dispatchReviewed}
                          onChange={(event) => setDispatchReviewed(event.target.checked)}
                        />
                        Confirmei que o lote está totalmente importado e solicito despacho nesta
                        conexão configurada.
                      </label>
                      <Button
                        disabled={!dispatchReviewed || dispatch.isPending}
                        onClick={() => dispatch.mutate()}
                      >
                        {dispatch.isPending
                          ? 'Solicitando despacho…'
                          : 'Solicitar despacho externo'}
                      </Button>
                      <p>
                        HTTP 202 significa enfileirado, não aceite da transportadora nem envio
                        concluído.
                      </p>
                    </div>
                  )}
                  {dispatch.isError && <p role="alert">{message(dispatch.error)}</p>}
                  {dispatch.isSuccess && (
                    <p role="status">
                      Solicitação {display(dispatch.data.dispatch?.status ?? 'registrada')} ·
                      enfileirados {dispatch.data.dispatch?.enqueued ?? '—'} · aceitos{' '}
                      {dispatch.data.dispatch?.accepted ?? '—'} · rejeitados{' '}
                      {dispatch.data.dispatch?.rejected ?? '—'} · incertos{' '}
                      {dispatch.data.dispatch?.uncertain ?? '—'}. Aceite não representa entrega.
                    </p>
                  )}
                  <section className="import-activity">
                    <h3>Auditoria e snapshots externos</h3>
                    {detail.data.activity.map((event) => (
                      <details key={event.id}>
                        <summary>
                          {new Date(event.occurred_at).toLocaleString('pt-BR')} · {event.operation}{' '}
                          · {event.outcome}
                        </summary>
                        <pre>{JSON.stringify(event.details, null, 2)}</pre>
                      </details>
                    ))}
                  </section>
                </>
              )}
            </section>
          )}
        </div>
      )}
    </>
  );
}
