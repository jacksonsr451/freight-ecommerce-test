import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useMemo, useState } from 'react';
import { ApiError } from '../api/http';
import { getAdminOrder, listAdminOrders, transitionAdminFulfillment } from '../api/orders';
import type { AdminFulfillmentStatus } from '../api/orders';
import { money } from '../lib/format';
import { Button, EmptyState, PageHeading } from '../components/ui';

const fulfillmentLabels: Record<AdminFulfillmentStatus, string> = {
  pago_simulado: 'Pago simulado',
  separando: 'Separando',
  embalado: 'Embalado',
  pronto_para_importacao: 'Pronto para importação',
  importacao_pendente: 'Importação pendente (local)',
  expedido_simulado: 'Expedido (simulação local)',
  entregue_simulado: 'Entregue (simulação local)',
  cancelado: 'Cancelado localmente',
};

const nextStates: Partial<
  Record<AdminFulfillmentStatus, Exclude<AdminFulfillmentStatus, 'pago_simulado' | 'cancelado'>[]>
> = {
  pago_simulado: ['separando'],
  separando: ['embalado'],
  embalado: ['pronto_para_importacao', 'expedido_simulado'],
  pronto_para_importacao: ['importacao_pendente'],
  importacao_pendente: ['pronto_para_importacao', 'expedido_simulado'],
  expedido_simulado: ['entregue_simulado'],
};

const orderLabels: Record<string, string> = {
  payment_pending: 'Pagamento pendente',
  paid_simulated: 'Pago simulado',
  payment_declined: 'Pagamento recusado',
  cancelled: 'Cancelado localmente',
};

function errorMessage(error: unknown) {
  return error instanceof ApiError ? error.message : 'Não foi possível acessar os pedidos locais.';
}

function pretty(value: unknown) {
  return JSON.stringify(value, null, 2);
}

export default function AdminOrdersPage() {
  const [key, setKey] = useState('');
  const [authSession, setAuthSession] = useState(0);
  const [orderStatus, setOrderStatus] = useState('');
  const [fulfillmentStatus, setFulfillmentStatus] = useState('');
  const [selectedOrder, setSelectedOrder] = useState('');
  const queryClient = useQueryClient();
  const filters = useMemo(
    () => ({ orderStatus, fulfillmentStatus }),
    [orderStatus, fulfillmentStatus],
  );
  const list = useQuery({
    queryKey: ['admin-orders', authSession, filters],
    enabled: key.trim().length >= 32,
    retry: false,
    queryFn: ({ signal }) => listAdminOrders(key.trim(), filters, signal),
  });
  const selected = useQuery({
    queryKey: ['admin-order', authSession, selectedOrder],
    enabled: key.trim().length >= 32 && Boolean(selectedOrder),
    retry: false,
    queryFn: ({ signal }) => getAdminOrder(key.trim(), selectedOrder, signal),
  });
  const transition = useMutation({
    retry: false,
    mutationFn: (status: Exclude<AdminFulfillmentStatus, 'pago_simulado' | 'cancelado'>) => {
      const current = selected.data?.internal_fulfillment_status;
      if (!current) throw new Error('O pedido ainda não possui fulfillment local.');
      return transitionAdminFulfillment(key.trim(), selectedOrder, current, status);
    },
    onSuccess: async (detail) => {
      queryClient.setQueryData(['admin-order', authSession, selectedOrder], detail);
      await queryClient.invalidateQueries({ queryKey: ['admin-orders', authSession] });
    },
    onError: () => {
      void selected.refetch();
    },
  });
  const detail = selected.data;
  const currentStatus = detail?.internal_fulfillment_status;
  const available = currentStatus ? (nextStates[currentStatus] ?? []) : [];

  return (
    <>
      <PageHeading eyebrow="Operação local" title="Painel administrativo de pedidos">
        Acompanhe snapshots e avance somente o fulfillment simulado. Esta tela não chama a API
        Packsenvios nem altera status externo.
      </PageHeading>
      <section className="surface-card admin-access">
        <label htmlFor="admin-key">Chave administrativa local</label>
        <input
          id="admin-key"
          type="password"
          autoComplete="off"
          value={key}
          onChange={(event) => {
            setKey(event.target.value);
            setAuthSession((session) => session + 1);
            setSelectedOrder('');
          }}
          placeholder="Informe a chave local configurada no backend"
        />
        <p>
          A chave é mantida somente na memória desta tela e enviada no cabeçalho local de
          administração.
        </p>
      </section>

      {key.trim().length < 32 ? (
        <EmptyState title="Autenticação administrativa necessária">
          Informe a chave local autorizada para carregar pedidos e auditoria.
        </EmptyState>
      ) : list.isError ? (
        <section className="state-panel error-state" role="alert">
          <h2>Pedidos indisponíveis</h2>
          <p>{errorMessage(list.error)}</p>
          <Button onClick={() => void list.refetch()}>Tentar novamente</Button>
        </section>
      ) : list.isPending ? (
        <section className="state-panel" role="status">
          Carregando pedidos locais…
        </section>
      ) : (
        <div className="admin-orders-layout">
          <section className="surface-card admin-order-queue">
            <div className="admin-filters">
              <label>
                Estado do pedido
                <select
                  value={orderStatus}
                  onChange={(event) => setOrderStatus(event.target.value)}
                >
                  <option value="">Todos</option>
                  {Object.entries(orderLabels).map(([value, label]) => (
                    <option key={value} value={value}>
                      {label}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Estado interno
                <select
                  value={fulfillmentStatus}
                  onChange={(event) => setFulfillmentStatus(event.target.value)}
                >
                  <option value="">Todos</option>
                  {Object.entries(fulfillmentLabels).map(([value, label]) => (
                    <option key={value} value={value}>
                      {label}
                    </option>
                  ))}
                </select>
              </label>
            </div>
            <h2>Pedidos ({list.data.total})</h2>
            {list.data.items.length === 0 ? (
              <p>Nenhum pedido corresponde aos filtros.</p>
            ) : (
              <div className="admin-order-list">
                {list.data.items.map((order) => (
                  <button
                    type="button"
                    className={`admin-order-row ${selectedOrder === order.id ? 'selected' : ''}`}
                    key={order.id}
                    onClick={() => setSelectedOrder(order.id)}
                  >
                    <strong>Pedido · {order.id.slice(0, 8)}</strong>
                    <span>{orderLabels[order.status]}</span>
                    <span>
                      {order.fulfillment
                        ? fulfillmentLabels[order.fulfillment.status]
                        : 'Sem fulfillment'}
                    </span>
                    <span>{money(order.total_cents)}</span>
                  </button>
                ))}
              </div>
            )}
          </section>

          <section className="admin-order-detail" aria-live="polite">
            {!selectedOrder ? (
              <EmptyState title="Selecione um pedido">
                Detalhes, snapshots e auditoria aparecem aqui.
              </EmptyState>
            ) : selected.isError ? (
              <div className="state-panel error-state" role="alert">
                {errorMessage(selected.error)}
              </div>
            ) : selected.isPending || !detail ? (
              <div className="state-panel" role="status">
                Carregando detalhe local…
              </div>
            ) : (
              <>
                <section className="surface-card">
                  <p className="eyebrow">Pedido local · {detail.order.id}</p>
                  <h2>Detalhe e operação</h2>
                  <dl className="admin-status-grid">
                    <dt>Pedido</dt>
                    <dd>{orderLabels[detail.order.status]}</dd>
                    <dt>Fulfillment interno</dt>
                    <dd>
                      {currentStatus ? fulfillmentLabels[currentStatus] : 'Ainda não iniciado'}
                    </dd>
                    <dt>Status externo</dt>
                    <dd>{detail.external_status ?? 'Sem status externo vinculado'}</dd>
                    <dt>Pagamento</dt>
                    <dd>{detail.order.payment.status} · simulação</dd>
                  </dl>
                  {currentStatus && available.length > 0 && (
                    <div className="admin-transition-actions">
                      <p>Próxima etapa local:</p>
                      {available.map((status) => (
                        <Button
                          key={status}
                          disabled={transition.isPending}
                          onClick={() => transition.mutate(status)}
                        >
                          {transition.isPending ? 'Atualizando…' : fulfillmentLabels[status]}
                        </Button>
                      ))}
                    </div>
                  )}
                  {transition.isError && (
                    <p className="cart-error" role="alert">
                      {errorMessage(transition.error)}
                    </p>
                  )}
                  {detail.order.freight_review_required && (
                    <p className="notice">
                      Oferta manual/demonstrativa: vínculo local apenas; não é contratação.
                    </p>
                  )}
                </section>

                <details className="surface-card admin-snapshots" open>
                  <summary>Snapshots preservados</summary>
                  <pre>{pretty(detail.snapshots)}</pre>
                </details>

                <section className="surface-card admin-timeline">
                  <h2>Auditoria e linha do tempo</h2>
                  {detail.timeline.length === 0 ? (
                    <p>Sem eventos registrados.</p>
                  ) : (
                    <ol>
                      {detail.timeline.map((event) => (
                        <li key={event.id}>
                          <strong>{event.title}</strong>
                          <span>{new Date(event.occurred_at).toLocaleString('pt-BR')}</span>
                          <span>Origem: {event.source}</span>
                          {event.internal_status && <span>Interno: {event.internal_status}</span>}
                          {event.external_status && <span>Externo: {event.external_status}</span>}
                          <details>
                            <summary>Snapshot do evento</summary>
                            <pre>{pretty(event.snapshot)}</pre>
                          </details>
                        </li>
                      ))}
                    </ol>
                  )}
                </section>
              </>
            )}
          </section>
        </div>
      )}
    </>
  );
}
