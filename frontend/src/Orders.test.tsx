import { QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, expect, it, vi } from 'vitest';
import App from './App';
import { createQueryClient } from './lib/query-client';
import { setCartReference } from './cart/reference';

const CART = '00000000-0000-4000-8000-000000000100';
const ORDER = '00000000-0000-4000-8000-000000000300';
const OPTION = '00000000-0000-4000-8000-000000000301';
const clients: ReturnType<typeof createQueryClient>[] = [];
function order(
  status:
    'payment_pending' | 'paid_simulated' | 'payment_declined' | 'cancelled' = 'payment_pending',
) {
  return {
    id: ORDER,
    status,
    simulation: true,
    created_at: '2026-10-09T12:00:00+00:00',
    cart_revision: 7,
    subtotal_cents: 4590,
    freight_cents: 2590,
    total_cents: 7180,
    selected_option_reference: OPTION,
    freight_review_required: true,
    shipping_destination: { postal_code: '01001000', city: 'São Paulo', state: 'SP' },
    items: [
      {
        product_id: '00000000-0000-4000-8000-000000000010',
        sku: 'SYNTHETIC',
        name: 'Produto local',
        quantity: 1,
        unit_price_cents: 4590,
        line_total_cents: 4590,
        product_snapshot: { synthetic_fixture: true },
      },
    ],
    payment: {
      id: '00000000-0000-4000-8000-000000000302',
      status:
        status === 'paid_simulated'
          ? 'approved'
          : status === 'payment_declined'
            ? 'declined'
            : 'pending',
      amount_cents: 7180,
      simulation: true,
    },
    fulfillment:
      status === 'paid_simulated'
        ? { status: 'pago_simulado', tracking_source: 'simulated' }
        : status === 'cancelled'
          ? { status: 'cancelado', tracking_source: 'simulated' }
          : null,
    cancellation_reason:
      status === 'payment_declined'
        ? 'payment_declined'
        : status === 'cancelled'
          ? 'operator_cancelled'
          : null,
  };
}
function mount(path: string, initial = order()) {
  let state = initial;
  const calls: { path: string; method: string; body: Record<string, unknown> | null }[] = [];
  const fetchMock = vi.fn(async (url: string, options: RequestInit = {}) => {
    const body = options.body
      ? (JSON.parse(String(options.body)) as Record<string, unknown>)
      : null;
    calls.push({ path: url, method: options.method ?? 'GET', body });
    if (url === `/api/orders/${ORDER}`) return new Response(JSON.stringify(state));
    if (url === `/api/orders/${ORDER}/confirm` && options.method === 'POST') {
      const outcome = body?.outcome;
      if (outcome === 'approved') state = order('paid_simulated');
      else if (outcome === 'declined') state = order('payment_declined');
      return new Response(JSON.stringify(state));
    }
    if (url === `/api/orders/${ORDER}/cancel` && options.method === 'POST') {
      state = order('cancelled');
      return new Response(JSON.stringify(state));
    }
    if (url.startsWith(`/api/carts/${CART}/orders?`))
      return new Response(JSON.stringify({ items: [state], total: 1 }));
    return new Response('{}', { status: 404 });
  });
  vi.stubGlobal('fetch', fetchMock);
  setCartReference(CART);
  const client = createQueryClient();
  clients.push(client);
  render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[path]}>
        <App />
      </MemoryRouter>
    </QueryClientProvider>,
  );
  return { calls, fetchMock };
}
afterEach(() => {
  clients.forEach((client) => client.clear());
  clients.length = 0;
  setCartReference(null);
});

it('simula aprovação, mostra fulfillment local e pode compensar reserva local', async () => {
  const { calls } = mount(`/pedidos/${ORDER}`);
  const user = userEvent.setup();
  expect(await screen.findByRole('heading', { name: 'Resumo do pedido' })).toBeVisible();
  expect(screen.getByText(/pagamento desta tela são simulações da loja/)).toBeVisible();
  expect(screen.getByText(/Não significa seleção\/contratação automática/)).toBeVisible();
  await user.click(screen.getByRole('button', { name: 'Simular aprovado' }));
  expect(await screen.findByText(/Pagamento aprovado \(simulação local\)/)).toBeVisible();
  expect(screen.getByText(/pago simulado · evento de origem simulated/)).toBeVisible();
  expect(calls.find((call) => call.path.endsWith('/confirm'))?.body).toEqual({
    expected_cart_revision: 7,
    outcome: 'approved',
  });
  await user.click(screen.getByRole('button', { name: /Cancelar pedido local/ }));
  expect(await screen.findByText(/Pedido cancelado \(simulação local\)/)).toBeVisible();
  expect(calls.find((call) => call.path.endsWith('/cancel'))?.body).toEqual({
    expected_cart_revision: 7,
  });
  expect(calls.every((call) => !call.path.startsWith('/api/v1/freight'))).toBe(true);
});

it('permite manter pendente e simular recusa sem declarar cobrança real', async () => {
  mount(`/pedidos/${ORDER}`);
  const user = userEvent.setup();
  await user.click(await screen.findByRole('button', { name: 'Manter pendente' }));
  expect(await screen.findByText(/Aguardando decisão do simulador/)).toBeVisible();
  await user.click(screen.getByRole('button', { name: 'Simular recusado' }));
  expect(await screen.findByText(/Pagamento recusado \(simulação local\)/)).toBeVisible();
  expect(screen.getByText(/Nenhum estoque foi reservado/)).toBeVisible();
  expect(screen.getByRole('button', { name: 'Começar novo carrinho' })).toBeVisible();
});

it('mostra histórico somente para a referência de carrinho local', async () => {
  mount('/pedidos');
  expect(await screen.findByRole('link', { name: /Pedido local · 00000000/ })).toBeVisible();
  expect(
    screen.getByText(/Pedidos, pagamentos e estados de fulfillment desta loja simulada/),
  ).toBeVisible();
});

it('oculta detalhes pessoais, erro bruto e não envia chave ou preço na simulação', async () => {
  const { calls } = mount(`/pedidos/${ORDER}`);
  const user = userEvent.setup();
  await user.click(await screen.findByRole('button', { name: 'Simular aprovado' }));
  await screen.findByText(/Pagamento aprovado \(simulação local\)/);
  expect(screen.queryByText('buyer@example.com')).not.toBeInTheDocument();
  expect(calls.find((call) => call.path.endsWith('/confirm'))?.body).not.toHaveProperty(
    'amount_cents',
  );
});
