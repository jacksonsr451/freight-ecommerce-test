import { QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, expect, it, vi } from 'vitest';
import App from './App';
import { createQueryClient } from './lib/query-client';

const ORDER = '00000000-0000-4000-8000-000000000300';
const ADMIN_KEY = 'synthetic-local-admin-key-for-tests-only';
const payment = {
  id: '00000000-0000-4000-8000-000000000302',
  status: 'approved',
  amount_cents: 7180,
  simulation: true,
};

function order(status: string) {
  return {
    id: ORDER,
    status: 'paid_simulated',
    simulation: true,
    created_at: '2026-10-09T12:00:00+00:00',
    cart_revision: 7,
    subtotal_cents: 4590,
    freight_cents: 2590,
    total_cents: 7180,
    selected_option_reference: '00000000-0000-4000-8000-000000000301',
    freight_review_required: true,
    shipping_destination: { postal_code: '01001000', city: 'São Paulo', state: 'SP' },
    items: [],
    payment,
    fulfillment: { status, tracking_source: 'simulated' },
  };
}

function detail(status: string) {
  return {
    order: order(status),
    snapshots: {
      shipping_address: { city: 'São Paulo' },
      freight_option: { manual_only: true, payload: { synthetic_fixture: true } },
      products: [{ sku: 'SYNTHETIC' }],
    },
    internal_fulfillment_status: status,
    external_status: null,
    timeline: [
      {
        id: '00000000-0000-4000-8000-000000000310',
        occurred_at: '2026-10-09T12:01:00+00:00',
        source: 'simulated',
        event_key: `admin-${status}`,
        title: `Etapa local ${status}`,
        internal_status: status,
        external_status: null,
        snapshot: { simulation: true, synthetic_fixture: true },
      },
    ],
  };
}

afterEach(() => vi.unstubAllGlobals());

it('requires local admin credential before making requests', async () => {
  const fetchMock = vi.fn();
  vi.stubGlobal('fetch', fetchMock);
  const client = createQueryClient();
  render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={['/admin/pedidos']}>
        <App />
      </MemoryRouter>
    </QueryClientProvider>,
  );
  expect(await screen.findByText(/Informe a chave local autorizada/)).toBeVisible();
  expect(
    fetchMock.mock.calls.every(([path]) => !String(path).startsWith('/api/admin/orders')),
  ).toBe(true);
  client.clear();
});

it('shows local snapshots and audit, advances only internal status, and sends local admin header', async () => {
  let current = 'pago_simulado';
  const fetchMock = vi.fn(async (input: string, init: RequestInit = {}) => {
    const path = String(input);
    if (path.startsWith('/api/admin/orders?'))
      return new Response(JSON.stringify({ items: [order(current)], total: 1 }));
    if (path === `/api/admin/orders/${ORDER}/fulfillment` && init.method === 'POST') {
      const body = JSON.parse(String(init.body)) as { status: string };
      current = body.status;
      return new Response(JSON.stringify(detail(current)));
    }
    if (path === `/api/admin/orders/${ORDER}`) return new Response(JSON.stringify(detail(current)));
    return new Response('{}', { status: 404 });
  });
  vi.stubGlobal('fetch', fetchMock);
  const client = createQueryClient();
  const user = userEvent.setup();
  render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={['/admin/pedidos']}>
        <App />
      </MemoryRouter>
    </QueryClientProvider>,
  );
  await user.type(screen.getByLabelText('Chave administrativa local'), ADMIN_KEY);
  await user.click(await screen.findByRole('button', { name: /Pedido · 00000000/ }));
  expect(await screen.findByText('Sem status externo vinculado')).toBeVisible();
  expect(screen.getByText(/Oferta manual\/demonstrativa/)).toBeVisible();
  expect(screen.getByText(/Origem: simulated/)).toBeVisible();
  expect(screen.getByText(/SYNTHETIC/)).toBeVisible();
  await user.click(screen.getByRole('button', { name: 'Separando' }));
  expect(await screen.findByText('Interno: separando')).toBeVisible();
  await waitFor(() => expect(current).toBe('separando'));
  const mutation = fetchMock.mock.calls.find(([, init]) => init?.method === 'POST');
  expect(mutation?.[1]?.headers).toMatchObject({ 'X-Local-Admin-Key': ADMIN_KEY });
  expect(mutation?.[1]?.headers).not.toHaveProperty('Authorization');
  client.clear();
});
