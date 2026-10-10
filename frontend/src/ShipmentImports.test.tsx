import { QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, expect, it, vi } from 'vitest';
import App from './App';
import { createQueryClient } from './lib/query-client';

const ADMIN_KEY = 'synthetic-local-admin-key-for-tests-only';
const BATCH = '00000000-0000-4000-8000-000000000004';

function localBatch(
  status = 'upload_pending',
  externalStatus: string | null = 'queued',
  complete = false,
) {
  return {
    id: BATCH,
    filename: 'synthetic-orders.csv',
    local_status: status,
    external_status: externalStatus,
    total: complete ? 1 : 2,
    valid: 1,
    invalid: complete ? 0 : 1,
    imported: complete ? 1 : 0,
    duplicates: 0,
    processed: complete ? 1 : 0,
    created_at: '2026-10-10T12:00:00+00:00',
    dispatch_request_id: null,
    dispatch_status: null,
  };
}

function detail(
  status: string,
  complete = false,
  dispatch: Record<string, unknown> | null = null,
  dispatchBlocked = false,
) {
  return {
    batch: localBatch(
      status === 'review'
        ? 'ready_for_confirmation'
        : status === 'imported'
          ? 'imported'
          : 'confirmation_pending',
      status,
      complete,
    ),
    external_status: status,
    issue: null,
    items: [
      {
        row: complete ? 37 : 3,
        status: complete ? 'synthetic_imported' : 'invalid',
        recipientName: 'Destinatário sintético',
        destination: '01001000',
        errors: complete ? [] : ['synthetic_validation_issue'],
        shipmentId: complete ? 'synthetic-shipment-id' : null,
        dispatchStatus: null,
      },
    ],
    has_more: false,
    next_cursor: null,
    dispatch,
    dispatch_retry_blocked: dispatchBlocked,
    activity: [],
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
          dispatch_connection_configured: true,
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
          dispatch_connection_configured: false,
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

it('requires explicit dispatch confirmation and keeps queued separate from carrier acceptance', async () => {
  const dispatchSnapshot = {
    id: 'synthetic-dispatch-request-001',
    batchId: BATCH,
    connectionId: '00000000-0000-4000-8000-000000000005',
    status: 'queued',
    total: 1,
    enqueued: 1,
    accepted: 0,
    rejected: 0,
    uncertain: 0,
    issue: null,
  };
  let persistedDispatch: typeof dispatchSnapshot | null = null;
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
          dispatch_connection_configured: true,
        }),
      );
    if (path === '/api/admin/imports/export-readiness')
      return new Response(JSON.stringify({ can_export: false, missing_fields: [] }));
    if (path === '/api/admin/imports' && init.method === 'POST')
      return new Response(JSON.stringify(localBatch()), { status: 202 });
    if (path === '/api/admin/imports')
      return new Response(JSON.stringify({ items: [localBatch()], total: 1 }));
    if (path.startsWith(`/api/admin/imports/${BATCH}?`))
      return new Response(
        JSON.stringify(detail('imported', true, persistedDispatch, Boolean(persistedDispatch))),
      );
    if (path === `/api/admin/imports/${BATCH}/dispatch` && init.method === 'POST') {
      persistedDispatch = dispatchSnapshot;
      return new Response(
        JSON.stringify({
          batch: {
            ...localBatch('dispatch_pending', 'imported', true),
            dispatch_request_id: dispatchSnapshot.id,
            dispatch_status: dispatchSnapshot.status,
          },
          dispatch: dispatchSnapshot,
          dispatch_retry_blocked: true,
          reconciliation_required: false,
        }),
        { status: 202 },
      );
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
  const file = new File(['synthetic fixture'], 'synthetic-orders.csv', { type: 'text/csv' });
  await user.upload(screen.getByLabelText('Arquivo CSV ou XLSX do modelo atual'), file);
  await user.click(await screen.findByRole('button', { name: /Lote 00000000/ }));
  expect(await screen.findAllByText('imported')).toHaveLength(2);
  const dispatchButton = await screen.findByRole('button', { name: 'Solicitar despacho externo' });
  expect(dispatchButton).toBeDisabled();
  await user.click(screen.getByLabelText(/Confirmei que o lote está totalmente importado/));
  await user.click(dispatchButton);
  expect(await screen.findByText(/enfileirados 1 · aceitos 0/)).toBeVisible();
  expect(screen.queryByText(/entregue/i)).not.toBeInTheDocument();
  const dispatchCall = fetchMock.mock.calls.find(
    ([path, init]) => path === `/api/admin/imports/${BATCH}/dispatch` && init?.method === 'POST',
  );
  expect(dispatchCall?.[1]?.headers).toMatchObject({ 'X-Local-Admin-Key': ADMIN_KEY });
  expect(dispatchCall?.[1]?.headers).not.toHaveProperty('Authorization');
  expect(JSON.parse(String(dispatchCall?.[1]?.body))).toEqual({
    confirm_dispatch: true,
    operator_confirmed: true,
  });
  client.clear();
});

it('shows real tracking as a read-only snapshot and requests refresh without fabricating label links', async () => {
  const snapshot = {
    code: 'synthetic-code',
    reference: 'synthetic-reference',
    acceptedAt: null,
    updatedAt: '2026-10-10T12:00:00+00:00',
    issue: null,
    labels: [],
    labelsAt: null,
    events: [
      { fixture: 'later event', synthetic_order: 2 },
      { fixture: 'earlier event', synthetic_order: 1 },
    ],
  };
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
          dispatch_connection_configured: false,
        }),
      );
    if (path === '/api/admin/imports/export-readiness')
      return new Response(JSON.stringify({ can_export: false, missing_fields: [] }));
    if (path === '/api/admin/imports' && init.method === 'POST')
      return new Response(JSON.stringify(localBatch()), { status: 202 });
    if (path === '/api/admin/imports')
      return new Response(JSON.stringify({ items: [localBatch()], total: 1 }));
    if (path.startsWith(`/api/admin/imports/${BATCH}?`))
      return new Response(JSON.stringify(detail('imported', true)));
    if (path === `/api/admin/imports/${BATCH}/rows/37/tracking` && init.method === 'GET')
      return new Response(
        JSON.stringify({
          batch_id: BATCH,
          row_number: 37,
          source: 'packsenvios',
          snapshot,
          captured_at: '2026-10-10T12:01:00+00:00',
          refresh_queued: false,
        }),
      );
    if (path === `/api/admin/imports/${BATCH}/rows/37/tracking` && init.method === 'POST')
      return new Response(
        JSON.stringify({
          batch_id: BATCH,
          row_number: 37,
          source: 'packsenvios',
          status: 'queued',
        }),
        { status: 202 },
      );
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
  const file = new File(['synthetic fixture'], 'synthetic-orders.csv', { type: 'text/csv' });
  await user.upload(screen.getByLabelText('Arquivo CSV ou XLSX do modelo atual'), file);
  await user.click(await screen.findByRole('button', { name: /Lote 00000000/ }));
  await user.click(
    await screen.findByRole('button', { name: /Consultar snapshot real · linha 37/ }),
  );
  expect(await screen.findByText(/synthetic-code/)).toBeVisible();
  expect(screen.getByText(/"synthetic_order": 2/)).toBeVisible();
  expect(screen.getByText(/"synthetic_order": 1/)).toBeVisible();
  expect(screen.getByText(/não há download nesta tela/)).toBeVisible();
  await user.click(screen.getByRole('button', { name: /Solicitar atualização · linha 37/ }));
  expect(await screen.findByText(/Atualização solicitada; status queued/)).toBeVisible();
  const calls = fetchMock.mock.calls;
  expect(calls.some(([path]) => String(path).endsWith('/rows/37/tracking'))).toBe(true);
  expect(
    calls.some(
      ([path]) =>
        String(path).endsWith('/rows/37/tracking') && !String(path).includes('/api/admin'),
    ),
  ).toBe(false);
  expect(screen.queryByRole('link', { name: /etiqueta|download/i })).not.toBeInTheDocument();
  client.clear();
});
