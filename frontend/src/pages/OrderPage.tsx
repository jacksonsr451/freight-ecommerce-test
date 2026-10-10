import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { ApiError } from '../api/http';
import { cancelLocalOrder, confirmLocalPayment, getLocalOrder } from '../api/orders';
import type { LocalOrder } from '../api/orders';
import { cartKey } from '../cart/queries';
import { setCartReference } from '../cart/reference';
import { money } from '../lib/format';
import { Button, ErrorState, LoadingState, PageHeading } from '../components/ui';

function label(status: string) {
  return (
    (
      {
        payment_pending: 'Aguardando decisão do simulador',
        paid_simulated: 'Pagamento aprovado (simulação local)',
        payment_declined: 'Pagamento recusado (simulação local)',
        cancelled: 'Pedido cancelado (simulação local)',
      } as Record<string, string>
    )[status] ?? status
  );
}

export default function OrderPage() {
  const { orderId = '' } = useParams();
  const client = useQueryClient();
  const navigate = useNavigate();
  const query = useQuery({
    queryKey: ['local-order', orderId],
    enabled: Boolean(orderId),
    retry: false,
    queryFn: ({ signal }) => getLocalOrder(orderId, signal),
  });
  const refresh = async (order: LocalOrder) => {
    client.setQueryData(['local-order', order.id], order);
    await Promise.all([
      client.invalidateQueries({ queryKey: ['local-orders'] }),
      client.invalidateQueries({ queryKey: cartKey(null), exact: false }),
      client.invalidateQueries({ queryKey: ['cart'] }),
    ]);
  };
  const payment = useMutation({
    mutationKey: ['payment-simulation', orderId],
    retry: false,
    mutationFn: (outcome: 'approved' | 'declined' | 'pending') =>
      confirmLocalPayment(orderId, query.data!.cart_revision, outcome),
    onSuccess: refresh,
    onError: () => {
      void query.refetch();
    },
  });
  const cancel = useMutation({
    mutationKey: ['local-order-cancel', orderId],
    retry: false,
    mutationFn: () => cancelLocalOrder(orderId, query.data!.cart_revision),
    onSuccess: refresh,
    onError: () => {
      void query.refetch();
    },
  });
  if (query.isPending)
    return (
      <>
        <PageHeading eyebrow="Pedido local" title="Confirmação do pedido">
          Lendo estado da loja.
        </PageHeading>
        <LoadingState label="Carregando pedido…" />
      </>
    );
  if (query.isError)
    return (
      <>
        <PageHeading eyebrow="Pedido local" title="Confirmação do pedido">
          Este pedido é identificado pela API local.
        </PageHeading>
        <ErrorState
          message={
            query.error instanceof ApiError ? query.error.message : 'Pedido local indisponível.'
          }
          onRetry={() => {
            void query.refetch();
          }}
        />
      </>
    );
  const order = query.data;
  const actionError = payment.error ?? cancel.error;
  const busy = payment.isPending || cancel.isPending;
  return (
    <>
      <PageHeading eyebrow={`Pedido local · ${order.id.slice(0, 8)}`} title="Confirmação do pedido">
        O pedido e qualquer pagamento desta tela são simulações da loja. Nenhuma contratação ou
        cobrança externa ocorreu.
      </PageHeading>
      <div className="order-confirmation-grid">
        <div>
          <section className="surface-card">
            <span className={`stock-pill ${order.status === 'paid_simulated' ? '' : 'out'}`}>
              {label(order.status)}
            </span>
            <p className="eyebrow order-simulation-label">SIMULATION = TRUE</p>
            <h2>Resumo do pedido</h2>
            <p>
              Destino: {order.shipping_destination.city} · {order.shipping_destination.state} · CEP{' '}
              {order.shipping_destination.postal_code}
            </p>
            <div className="order-lines">
              {order.items.map((item) => (
                <div key={item.product_id} className="order-line">
                  <span>
                    {item.quantity} × {item.name}
                  </span>
                  <strong>{money(item.line_total_cents)}</strong>
                </div>
              ))}
            </div>
            <dl className="order-totals">
              <dt>Produtos</dt>
              <dd>{money(order.subtotal_cents)}</dd>
              <dt>Frete selecionado localmente</dt>
              <dd>{money(order.freight_cents)}</dd>
              <dt>Total simulado</dt>
              <dd>{money(order.total_cents)}</dd>
            </dl>
            {order.freight_review_required && (
              <p className="notice">
                Oferta manual ou demonstrativa: o vínculo é apenas local. Não significa
                seleção/contratação automática da rede.
              </p>
            )}
          </section>
          {order.fulfillment && (
            <section className="surface-card local-fulfillment">
              <h2>Fulfillment local</h2>
              <p>
                {order.fulfillment.status.replaceAll('_', ' ')} · evento de origem{' '}
                {order.fulfillment.tracking_source}
              </p>
              <p>Este estado é simulado e não afirma expedição ou entrega externa.</p>
            </section>
          )}
        </div>
        <aside className="summary-card payment-simulation">
          <p className="eyebrow">Gateway inexistente</p>
          <h2>Simulação de pagamento</h2>
          <p>
            Estado registrado: <strong>{order.payment.status}</strong>
          </p>
          <p>Valor: {money(order.payment.amount_cents)}</p>
          {order.payment.simulation && order.status === 'payment_pending' && (
            <>
              <p>Escolha um resultado local de teste:</p>
              <div className="payment-actions">
                <Button disabled={busy} onClick={() => payment.mutate('approved')}>
                  {payment.isPending ? 'Processando…' : 'Simular aprovado'}
                </Button>
                <Button
                  className="button-secondary"
                  disabled={busy}
                  onClick={() => payment.mutate('declined')}
                >
                  Simular recusado
                </Button>
                <Button
                  className="button-secondary"
                  disabled={busy}
                  onClick={() => payment.mutate('pending')}
                >
                  Manter pendente
                </Button>
              </div>
            </>
          )}
          {actionError && (
            <p role="alert" className="cart-error">
              {actionError instanceof ApiError
                ? actionError.message
                : 'Não foi possível atualizar o pedido.'}
            </p>
          )}
          {order.status === 'payment_declined' && (
            <p className="notice">
              Nenhum estoque foi reservado. O pedido recusado não é reaberto; inicie uma nova
              compra.
            </p>
          )}
          {order.status === 'paid_simulated' && order.fulfillment?.status === 'pago_simulado' && (
            <Button className="button-secondary" disabled={busy} onClick={() => cancel.mutate()}>
              {cancel.isPending ? 'Cancelando…' : 'Cancelar pedido local e liberar estoque'}
            </Button>
          )}
          <Link className="back-link" to="/pedidos">
            Ver histórico local
          </Link>
          {(order.status === 'payment_declined' || order.status === 'cancelled') && (
            <Button
              className="button-secondary"
              onClick={() => {
                setCartReference(null);
                void client.removeQueries({ queryKey: ['cart'] });
                navigate('/catalogo');
              }}
            >
              Começar novo carrinho
            </Button>
          )}
        </aside>
      </div>
    </>
  );
}
