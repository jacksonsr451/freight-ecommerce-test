import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import App from './App';

describe('bootstrap local', () => {
  it('renderiza e confirma o healthcheck da API local', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(
        new Response(JSON.stringify({ status: 'ok', service: 'freight-ecommerce-test' })),
      );
    vi.stubGlobal('fetch', fetchMock);
    render(<App />);
    expect(screen.getByRole('heading', { name: 'Freight Ecommerce Test' })).toBeVisible();
    expect(screen.getByRole('status')).toHaveTextContent('Verificando conexão');
    expect(await screen.findByText('API local conectada.')).toBeVisible();
    expect(fetchMock).toHaveBeenCalledWith('/api/health', {
      signal: expect.any(AbortSignal),
      headers: { Accept: 'application/json' },
    });
  });

  it('permite recuperar a conexão após falha sem exibir erro bruto', async () => {
    const fetchMock = vi.fn().mockRejectedValueOnce(new Error('synthetic-private-detail'));
    fetchMock.mockResolvedValueOnce(
      new Response(JSON.stringify({ status: 'ok', service: 'freight-ecommerce-test' })),
    );
    vi.stubGlobal('fetch', fetchMock);
    render(<App />);
    fireEvent.click(await screen.findByRole('button', { name: 'Tentar novamente' }));
    expect(await screen.findByText('API local conectada.')).toBeVisible();
    expect(screen.queryByText('synthetic-private-detail')).not.toBeInTheDocument();
  });

  it.each([
    new Response('indisponível', { status: 503 }),
    new Response(JSON.stringify({ status: 'unexpected' })),
  ])('não anuncia conexão para HTTP ou payload inválido', async (response) => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response));
    render(<App />);
    expect(await screen.findByRole('button', { name: 'Tentar novamente' })).toBeVisible();
    expect(screen.queryByText('API local conectada.')).not.toBeInTheDocument();
  });
});
