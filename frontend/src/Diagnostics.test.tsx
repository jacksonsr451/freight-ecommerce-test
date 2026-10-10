import { QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, expect, it, vi } from 'vitest';
import App from './App';
import { diagnosticReportJson } from './api/diagnostics';
import type { DiagnosticReport } from './api/diagnostics';
import { createQueryClient } from './lib/query-client';

const REQUEST_KEY = '00000000-0000-4000-8000-000000000011';
const QUOTE_ID = '00000000-0000-4000-8000-000000000012';
const EXTERNAL_QUOTE_ID = '00000000-0000-4000-8000-000000000014';
const CORRELATION = '00000000-0000-4000-8000-000000000013';
const SECRET_SENTINEL = 'synthetic-secret-must-not-appear-in-report';

function report(): DiagnosticReport {
  return {
    generated_at: '2026-10-10T12:00:00+00:00',
    freight_mode: 'real',
    purchases_simulated: true,
    checks: [
      { name: 'api', status: 'ok', latency_ms: 1, details: { process: 'running' } },
      {
        name: 'postgresql',
        status: 'ok',
        latency_ms: 4,
        details: { query: 'SELECT 1', connection_details_exposed: false },
      },
      {
        name: 'external_api',
        status: 'not_checked',
        latency_ms: null,
        details: { reason: 'not probed' },
      },
    ],
    operations: [
      {
        correlation_id: CORRELATION,
        operation: 'quote',
        mode: 'real',
        outcome: 'failed',
        occurred_at: '2026-10-10T11:59:00+00:00',
        http_status: 429,
        latency_ms: 231,
        request_key: REQUEST_KEY,
        quote_id: QUOTE_ID,
        external_quote_id: EXTERNAL_QUOTE_ID,
        import_batch_id: null,
        error_code: 'rate_limited',
        retry_after_seconds: 19,
        redacted_details: { packing_mode: 'equal_volumes', current: true },
        snapshot_summary: { redacted: true, field_count: 2, event_count: null, label_count: null },
      },
    ],
    pending_import_batches: 0,
    pending_webhook_receipts: 0,
  };
}

afterEach(() => vi.unstubAllGlobals());

it('shows correlation, request key, quote ID, latency, Retry-After and exports a redacted report', async () => {
  const fetchMock = vi.fn(async (input: string, init: RequestInit = {}) => {
    const path = String(input);
    if (path === '/api/health')
      return new Response(JSON.stringify({ status: 'ok', service: 'freight-ecommerce-test' }));
    if (path === '/api/runtime')
      return new Response(JSON.stringify({ freight_mode: 'real', purchases_simulated: true }));
    if (path === '/api/diagnostics') return new Response(JSON.stringify(report()));
    return new Response(JSON.stringify({ method: init.method ?? 'GET' }), { status: 404 });
  });
  vi.stubGlobal('fetch', fetchMock);
  const client = createQueryClient();
  const user = userEvent.setup();
  render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={['/diagnostico']}>
        <App />
      </MemoryRouter>
    </QueryClientProvider>,
  );
  expect(await screen.findByText(CORRELATION)).toBeVisible();
  expect(screen.getByText(REQUEST_KEY)).toBeVisible();
  expect(screen.getByText(QUOTE_ID)).toBeVisible();
  expect(screen.getByText(EXTERNAL_QUOTE_ID)).toBeVisible();
  expect(screen.getByText('19 s')).toBeVisible();
  expect(screen.getByText('231 ms')).toBeVisible();
  const createObjectUrls: Blob[] = [];
  const NativeURL = URL;
  class DownloadURL extends NativeURL {
    static createObjectURL(blob: Blob) {
      createObjectUrls.push(blob);
      return 'blob:diagnostic-report';
    }
    static revokeObjectURL() {}
  }
  vi.stubGlobal('URL', DownloadURL);
  const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {});
  await user.click(screen.getByRole('button', { name: 'Exportar relatório redigido' }));
  expect(createObjectUrls).toHaveLength(1);
  expect(createObjectUrls[0].type).toBe('application/json');
  expect(click).toHaveBeenCalledOnce();
  const exported = await createObjectUrls[0].text();
  expect(exported).toContain(CORRELATION);
  expect(exported).not.toContain(SECRET_SENTINEL);
  click.mockRestore();
  const json = diagnosticReportJson(report());
  expect(json).toContain(CORRELATION);
  expect(json).toContain(REQUEST_KEY);
  expect(json).not.toContain(SECRET_SENTINEL);
  expect(
    fetchMock.mock.calls.every(([, init]) => !init?.headers || !('Authorization' in init.headers)),
  ).toBe(true);
  await user.click(screen.getByRole('button', { name: 'Atualizar diagnóstico' }));
  expect(fetchMock.mock.calls.some(([path]) => path === '/api/diagnostics')).toBe(true);
  client.clear();
});

it('normalizes diagnostic network failures and never renders raw errors', async () => {
  const fetchMock = vi.fn(async (input: string) => {
    if (String(input) === '/api/health')
      return new Response(JSON.stringify({ status: 'ok', service: 'freight-ecommerce-test' }));
    if (String(input) === '/api/runtime')
      return new Response(JSON.stringify({ freight_mode: 'mock', purchases_simulated: true }));
    if (String(input) === '/api/diagnostics') throw new Error(SECRET_SENTINEL);
    return new Response('{}', { status: 404 });
  });
  vi.stubGlobal('fetch', fetchMock);
  const client = createQueryClient();
  render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={['/diagnostico']}>
        <App />
      </MemoryRouter>
    </QueryClientProvider>,
  );
  expect(await screen.findByRole('alert')).toBeVisible();
  expect(document.body.textContent).not.toContain(SECRET_SENTINEL);
  client.clear();
});
