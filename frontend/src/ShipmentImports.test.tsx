import { QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, expect, it, vi } from 'vitest';
import App from './App';
import { createQueryClient } from './lib/query-client';

const ADMIN_KEY = 'synthetic-local-admin-key-for-tests-only';
const BATCH = '00000000-0000-4000-8000-000000000004';

function localBatch(status = 'upload_pending', externalStatus: string | null = 'queued') {
  return {
    id: BATCH,
    filename: 'synthetic-orders.csv',
    local_status: status,
    external_status: externalStatus,
    total: 2,
    valid: 1,
    invalid: 1,
    imported: 0,
    duplicates: 0,
    processed: 0,
    created_at: '2026-10-10T12:00:00+00:00',
  };
}

function detail(status: string) {
  return {
    batch: localBatch(
      status === 'review' ? 'ready_for_confirmation' : 'confirmation_pending',
      status,
    ),
    external_status: status,
    issue: null,
    dispatch: null,
    items: [
      {
        row: 3,
        status: 'invalid',
        recipientName: 'Destinatário sintético',
        destination: '01001000',
        errors: ['synthetic_validation_issue'],
        shipmentId: null,
        dispatchStatus: null,
      },
    ],
    has_more: false,
    next_cursor: null,
  };
}

afterEach(() => vi.unstubAllGlobals());

it('requires local admin auth and explains why a valid local export is blocked', async () => {
  const fetchMock = vi.fn(async (input: string) => {
    void input;
    return new Response('{}');
  });
  vi.stubGlobal('fetch', fetchMock);
  const client = createQueryClient();
  render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={['/admin/importacao']}>
        <App />
      </MemoryRouter>
    </QueryClientProvider>,
  );
  expect(await screen.findByText(/Nenhuma credencial Packsenvios é solicitada/)).toBeVisible();
  expect(
    fetchMock.mock.calls.every(([path]) => !String(path).startsWith('/api/admin/imports')),
  ).toBe(true);
  client.clear();
});

it('uploads multipart only to the local API, reviews validation rows, and explicitly confirms async import', async () => {
  let externalStatus = 'review';
  const fetchMock = vi.fn(async (input: string, init: RequestInit = {}) => {
    const path = String(input);
    if (path === '/api/runtime') return new Response(JSON.stringify({ freight_mode: 'real' }));
    if (path === '/api/health') return new Response(JSON.stringify({ status: 'ok' }));
    if (path === '/api/admin/imports/availability')
      return new Response(
        JSON.stringify({
          mode: 'real',
          upload_enabled: true,
          company_configured: true,
          location_configured: true,
        }),
      );
    if (path === '/api/admin/imports/export-readiness')
      return new Response(
        JSON.stringify({
          can_export: false,
          missing_fields: ['nfe_access_key', 'recipient_document'],
        }),
      );
    if (path === '/api/admin/imports') {
      if (init.method === 'POST')
        return new Response(JSON.stringify(localBatch()), { status: 202 });
      return new Response(JSON.stringify({ items: [localBatch()], total: 1 }));
    }
    if (path.startsWith(`/api/admin/imports/${BATCH}?`))
      return new Response(JSON.stringify(detail(externalStatus)));
    if (path === `/api/admin/imports/${BATCH}/confirm` && init.method === 'POST') {
      externalStatus = 'confirming';
      return new Response(JSON.stringify(localBatch('confirmation_pending', externalStatus)), {
        status: 202,
      });
    }
    return new Response('{}', { status: 404 });
  });
  vi.stubGlobal('fetch', fetchMock);
  const client = createQueryClient();
  const user = userEvent.setup();
  render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={['/admin/importacao']}>
        <App />
      </MemoryRouter>
    </QueryClientProvider>,
  );
  await user.type(screen.getByLabelText('Chave administrativa local'), ADMIN_KEY);
  expect(await screen.findByText(/Exportação oficial bloqueada/)).toBeVisible();
  expect(screen.getByRole('button', { name: 'Exportação não disponível' })).toBeDisabled();
  const file = new File(['synthetic fixture'], 'synthetic-orders.csv', { type: 'text/csv' });
  await user.upload(screen.getByLabelText('Arquivo CSV ou XLSX do modelo atual'), file);
  expect(await screen.findByText(/Solicitação aceita pelo gateway/)).toBeVisible();
  expect(await screen.findByText(/synthetic_validation_issue/)).toBeVisible();
  expect(screen.getByText(/Estado externo/)).toBeVisible();
  expect(
    screen.queryByRole('button', { name: 'Confirmar linhas válidas' }),
  ).not.toBeInTheDocument();
  await user.click(screen.getByLabelText(/Revisei a página e as linhas exibidas/));
  const confirmButton = await screen.findByRole('button', { name: 'Confirmar linhas válidas' });
  expect(confirmButton).toBeEnabled();
  await user.click(confirmButton);
  expect(await screen.findByText(/Confirmação aceita/)).toBeVisible();
  await waitFor(() => expect(externalStatus).toBe('confirming'));

  const calls = fetchMock.mock.calls;
  const uploadCall = calls.find(
    ([, init]) => init?.method === 'POST' && init.body instanceof FormData,
  );
  expect(uploadCall?.[0]).toBe('/api/admin/imports');
  expect(uploadCall?.[1]?.headers).toMatchObject({ 'X-Local-Admin-Key': ADMIN_KEY });
  expect(uploadCall?.[1]?.headers).not.toHaveProperty('Authorization');
  expect(uploadCall?.[1]?.headers).not.toHaveProperty('Content-Type');
  expect(uploadCall?.[1]?.body).toBeInstanceOf(FormData);
  const detailCall = calls.find(([path]) => String(path).includes('errors_only=true'));
  expect(detailCall).toBeUndefined();
  client.clear();
});

it('requests the documented errors_only filter as the local boolean switch', async () => {
  const fetchMock = vi.fn(async (input: string) => {
    const path = String(input);
    if (path === '/api/runtime') return new Response(JSON.stringify({ freight_mode: 'mock' }));
    if (path === '/api/health') return new Response(JSON.stringify({ status: 'ok' }));
    if (path === '/api/admin/imports/availability')
      return new Response(
        JSON.stringify({
          mode: 'mock',
          upload_enabled: false,
          company_configured: false,
          location_configured: false,
        }),
      );
    if (path === '/api/admin/imports/export-readiness')
      return new Response(JSON.stringify({ can_export: false, missing_fields: [] }));
    if (path === '/api/admin/imports')
      return new Response(
        JSON.stringify({ items: [localBatch('ready_for_confirmation', 'review')], total: 1 }),
      );
    if (path.startsWith(`/api/admin/imports/${BATCH}?`))
      return new Response(JSON.stringify(detail('review')));
    return new Response('{}', { status: 404 });
  });
  vi.stubGlobal('fetch', fetchMock);
  const client = createQueryClient();
  const user = userEvent.setup();
  render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={['/admin/importacao']}>
        <App />
      </MemoryRouter>
    </QueryClientProvider>,
  );
  await user.type(screen.getByLabelText('Chave administrativa local'), ADMIN_KEY);
  await user.click(await screen.findByRole('button', { name: /Lote 00000000/ }));
  await screen.findByText(/synthetic_validation_issue/);
  await user.click(screen.getByLabelText(/Mostrar somente linhas com inconsistências/));
  await waitFor(() =>
    expect(fetchMock.mock.calls.some(([path]) => String(path).includes('errors_only=true'))).toBe(
      true,
    ),
  );
  expect(
    screen.queryByRole('button', { name: 'Confirmar linhas válidas' }),
  ).not.toBeInTheDocument();
  client.clear();
});
