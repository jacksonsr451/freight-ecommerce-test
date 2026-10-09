import { z } from 'zod';
import { describe, expect, it, vi } from 'vitest';
import { requestInternal } from './http';
import { getRuntime } from './runtime';

describe('cliente restrito à API local', () => {
  it.each([
    'https://packsenvios.example.test/api/v1/freight/quotes',
    '//other.example.test/api/health',
    '/api/v1/freight/quotes',
    '/api/%76%31/freight/quotes',
    '/api/../external',
    '/api/health#fragment',
  ])('recusa destino externo ou contrato direto antes de fetch: %s', async (path) => {
    const fetchMock = vi.fn();
    vi.stubGlobal('fetch', fetchMock);
    await expect(requestInternal(path, z.unknown())).rejects.toMatchObject({
      code: 'invalid-path',
    });
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('envia JSON sem Authorization e descarta extras da resposta', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(new Response(JSON.stringify({ ok: true, api_key: 'synthetic-private' })));
    vi.stubGlobal('fetch', fetchMock);
    const result = await requestInternal('/api/local-example', z.object({ ok: z.boolean() }), {
      method: 'POST',
      body: { quantity: 2 },
    });
    expect(result).toEqual({ ok: true });
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/local-example',
      expect.objectContaining({
        credentials: 'same-origin',
        method: 'POST',
        body: '{"quantity":2}',
        headers: { Accept: 'application/json', 'Content-Type': 'application/json' },
      }),
    );
  });

  it('normaliza falha de rede sem mensagem privada', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('synthetic-private-token')));
    await expect(getRuntime()).rejects.toMatchObject({
      code: 'network',
      message: 'Não foi possível conectar à API local.',
    });
  });

  it('preserva cancelamento para TanStack Query', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new DOMException('Aborted', 'AbortError')));
    await expect(getRuntime()).rejects.toMatchObject({ name: 'AbortError' });
  });

  it('não trata JSON quebrado como modo Mock', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('not json')));
    await expect(getRuntime()).rejects.toMatchObject({ code: 'invalid-response' });
  });
});
