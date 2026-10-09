import { QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';
import App from './App';
import { createQueryClient } from './lib/query-client';

const clients: ReturnType<typeof createQueryClient>[] = [];

function renderApp(path = '/catalogo') {
  const client = createQueryClient();
  clients.push(client);
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[path]}>
        <App />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

function successfulApi(mode: 'mock' | 'real' = 'mock') {
  const fetchMock = vi.fn().mockImplementation(async (path: string) => {
    if (path === '/api/health')
      return new Response(JSON.stringify({ status: 'ok', service: 'freight-ecommerce-test' }));
    if (path === '/api/runtime')
      return new Response(
        JSON.stringify({
          freight_mode: mode,
          purchases_simulated: true,
          api_key: 'synthetic-private-never-render',
        }),
      );
    throw new Error(`Unexpected test route ${path}`);
  });
  vi.stubGlobal('fetch', fetchMock);
  return fetchMock;
}

afterEach(() => {
  clients.forEach((client) => client.clear());
  clients.length = 0;
});

describe('shell de e-commerce local', () => {
  it('navega pelas cinco áreas e atualiza foco e indicação de página', async () => {
    const fetchMock = successfulApi();
    const user = userEvent.setup();
    renderApp('/');
    expect(
      await screen.findByRole('heading', { name: 'Uma compra de teste. Tudo às claras.' }),
    ).toBeVisible();
    expect(await screen.findByText('Mock · cotação sintética')).toBeVisible();
    const links = [
      ['Carrinho', 'Carrinho de compras'],
      ['Checkout', 'Checkout de teste'],
      ['Pedidos', 'Seus pedidos de teste'],
      ['Diagnóstico', 'Diagnóstico local'],
      ['Catálogo', 'Uma compra de teste. Tudo às claras.'],
    ];
    for (const [label, title] of links) {
      const link = within(screen.getByRole('navigation', { name: 'Principal' })).getByRole('link', {
        name: label,
      });
      await user.click(link);
      const heading = await screen.findByRole('heading', { name: title });
      expect(link).toHaveAttribute('aria-current', 'page');
      await waitFor(() => expect(heading).toHaveFocus());
    }
    expect(fetchMock.mock.calls.map(([path]) => path).sort()).toEqual([
      '/api/health',
      '/api/runtime',
    ]);
    expect(screen.queryByText('synthetic-private-never-render')).not.toBeInTheDocument();
  });

  it('usa modo Real apenas quando informado pelo backend e mantém compra simulada', async () => {
    successfulApi('real');
    renderApp();
    expect(await screen.findByText('Real · compra simulada')).toBeVisible();
    expect(screen.getByText('Compras e pagamentos sempre simulados')).toBeVisible();
  });

  it('não assume Mock enquanto a configuração está carregando', async () => {
    vi.stubGlobal('fetch', vi.fn().mockReturnValue(new Promise(() => {})));
    renderApp('/diagnostico');
    expect(screen.getByRole('status', { name: 'Modo da cotação' })).toHaveTextContent(
      'Verificando modo',
    );
    expect(screen.getByText('Verificando a API e o modo de cotação…')).toBeVisible();
    expect(screen.queryByText('Mock · cotação sintética')).not.toBeInTheDocument();
  });

  it('mostra erro seguro e permite recuperar os dois estados da API', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(new Response('synthetic-private-secret', { status: 503 }));
    vi.stubGlobal('fetch', fetchMock);
    const user = userEvent.setup();
    renderApp('/diagnostico');
    expect(await screen.findByRole('heading', { name: 'Não foi possível carregar' })).toBeVisible();
    expect(screen.getByRole('status', { name: 'Modo da cotação' })).toHaveTextContent(
      'Modo indisponível',
    );
    expect(screen.queryByText('synthetic-private-secret')).not.toBeInTheDocument();
    successfulApi();
    await user.click(screen.getByRole('button', { name: 'Tentar novamente' }));
    expect(await screen.findByRole('heading', { name: 'Aplicação local' })).toBeVisible();
    expect(await screen.findByText('Mock · cotação sintética')).toBeVisible();
  });

  it('sinaliza erro de resposta sem publicar configuração inválida', async () => {
    vi.stubGlobal(
      'fetch',
      vi
        .fn()
        .mockResolvedValue(
          new Response(JSON.stringify({ freight_mode: 'invented', api_key: 'synthetic-private' })),
        ),
    );
    renderApp('/diagnostico');
    expect(await screen.findByText('A resposta da API local não pôde ser validada.')).toBeVisible();
    expect(screen.queryByText('synthetic-private')).not.toBeInTheDocument();
  });

  it('apresenta vazio honesto e rota desconhecida com recuperação', async () => {
    successfulApi();
    const user = userEvent.setup();
    renderApp('/rota-inexistente');
    expect(screen.getByRole('heading', { name: 'Vamos voltar ao caminho certo?' })).toBeVisible();
    await user.click(screen.getByRole('link', { name: 'Voltar ao catálogo' }));
    expect(
      screen.getByRole('heading', { name: 'A vitrine está pronta para receber produtos' }),
    ).toBeVisible();
  });

  it('valida formulário por teclado, associa erro e preserva zero inicial sem enviar cotação', async () => {
    const fetchMock = successfulApi();
    const user = userEvent.setup();
    renderApp('/checkout');
    const input = screen.getByRole('textbox', { name: 'CEP de destino' });
    await user.click(input);
    await user.type(input, '123{Enter}');
    expect(screen.getByRole('alert')).toHaveTextContent('8 dígitos');
    expect(input).toHaveAttribute('aria-invalid', 'true');
    expect(input).toHaveFocus();
    const errorId = screen.getByRole('alert').id;
    expect(input.getAttribute('aria-describedby')).toContain(errorId);
    await user.clear(input);
    await user.type(input, '01001000{Enter}');
    expect(input).toHaveValue('01001000');
    expect(screen.getByText('CEP validado localmente. Nenhuma cotação foi enviada.')).toBeVisible();
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
    expect(
      fetchMock.mock.calls.every(
        ([path, options]) => String(path).startsWith('/api/') && options.method === 'GET',
      ),
    ).toBe(true);
  });

  it('fecha o menu com Escape e devolve foco ao controle', async () => {
    successfulApi();
    const user = userEvent.setup();
    renderApp();
    await user.click(screen.getByRole('button', { name: 'Abrir menu' }));
    expect(screen.getByRole('button', { name: 'Fechar menu' })).toHaveAttribute(
      'aria-expanded',
      'true',
    );
    await user.keyboard('{Escape}');
    expect(screen.getByRole('button', { name: 'Abrir menu' })).toHaveFocus();
    expect(screen.getByRole('button', { name: 'Abrir menu' })).toHaveAttribute(
      'aria-expanded',
      'false',
    );
  });
});
