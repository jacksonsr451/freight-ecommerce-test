import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { ApiError } from '../api/http';
import { listLocalOrders } from '../api/orders';
import { useCartReference } from '../cart/reference';
import { money } from '../lib/format';
import { EmptyState, ErrorState, LoadingState, PageHeading } from '../components/ui';

function orderStatus(status: string) {
  return (
    (
      {
        payment_pending: 'Aguardando pagamento simulado',
        paid_simulated: 'Pago (simulação local)',
        payment_declined: 'Pagamento recusado (simulação)',
        cancelled: 'Pedido cancelado localmente',
      } as Record<string, string>
    )[status] ?? 'Estado local'
  );
}

export default function OrdersPage() {
  const cartId = useCartReference();
  const orders = useQuery({
    queryKey: ['local-orders', cartId],
    enabled: cartId !== null,
    retry: false,
    queryFn: ({ signal }) => listLocalOrders(cartId!, 1, 20, signal),
  });
  let content;
  if (!cartId)
    content = (
      <EmptyState
        title="Ainda não há pedidos neste navegador"
        action={
          <Link className="button" to="/catalogo">
            Explorar catálogo
          </Link>
        }
      >
        Pedidos são locais e aparecem aqui depois que a loja cria um pedido de teste.
      </EmptyState>
    );
  else if (orders.isPending) content = <LoadingState label="Carregando histórico local…" />;
  else if (orders.isError)
    content = (
      <ErrorState
        message={
          orders.error instanceof ApiError ? orders.error.message : 'Histórico local indisponível.'
        }
        onRetry={() => {
          void orders.refetch();
        }}
      />
    );
  else if (orders.data.items.length === 0)
    content = (
      <EmptyState
        title="Nenhum pedido local ainda"
        action={
          <Link className="button" to="/catalogo">
            Escolher produtos
          </Link>
        }
      >
        Esta lista não consulta pedidos externos.
      </EmptyState>
    );
  else
    content = (
      <div className="order-list">
        {orders.data.items.map((order) => (
          <Link key={order.id} className="order-list-card" to={`/pedidos/${order.id}`}>
            <span className={`stock-pill ${order.status === 'paid_simulated' ? '' : 'out'}`}>
              {orderStatus(order.status)}
            </span>
            <strong>Pedido local · {order.id.slice(0, 8)}</strong>
            <span>{new Date(order.created_at).toLocaleString('pt-BR')}</span>
            <span>
              {order.items.length} linhas · {money(order.total_cents)}
            </span>
          </Link>
        ))}
      </div>
    );
  return (
    <>
      <PageHeading eyebrow="Histórico local" title="Seus pedidos de teste">
        Pedidos, pagamentos e estados de fulfillment desta loja simulada. Nenhum status representa
        um envio ou cobrança Packsenvios.
      </PageHeading>
      {content}
    </>
  );
}
