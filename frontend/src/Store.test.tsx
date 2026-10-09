import { QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';
import App from './App';
import { createQueryClient } from './lib/query-client';
import { BOOK, syntheticServer } from './test/store-server';
import { setCartReference } from './cart/reference';

const clients: ReturnType<typeof createQueryClient>[] = [];
function setup(path = '/catalogo') {
  const server = syntheticServer();
  vi.stubGlobal('fetch', vi.fn(server.fetcher));
  const client = createQueryClient();
  clients.push(client);
  render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[path]}>
        <App />
      </MemoryRouter>
    </QueryClientProvider>,
  );
  return { server, user: userEvent.setup() };
}
afterEach(() => {
  clients.forEach((client) => client.clear());
  clients.length = 0;
  setCartReference(null);
});

describe('jornada de catálogo e carrinho', () => {
  it('recupera uma falha transitória de GET sem repetir escrita', async () => {
    const { server, user } = setup(`/catalogo/${BOOK}`);
    await screen.findByRole('heading', { level: 1, name: 'Livro sintético' });
    let failed = false;
    vi.stubGlobal(
      'fetch',
      vi.fn(async (path: string, options?: RequestInit) => {
        if (path.startsWith('/api/carts/') && (options?.method ?? 'GET') === 'GET' && !failed) {
          failed = true;
          throw new Error('synthetic transient read failure');
        }
        return server.fetcher(path, options);
      }),
    );
    await user.click(screen.getByRole('button', { name: 'Adicionar ao carrinho' }));
    expect(await screen.findByRole('link', { name: 'Ver carrinho' })).toBeVisible();
    expect(failed).toBe(true);
    expect(
      server.calls.filter((call) => call.method === 'POST' && call.path.includes('/items')),
    ).toHaveLength(1);
  });
  it('não altera subtotal durante requisição pendente e desabilita alterações concorrentes', async () => {
    const { server, user } = setup(`/catalogo/${BOOK}`);
    await screen.findByRole('heading', { level: 1, name: 'Livro sintético' });
    await user.click(screen.getByRole('button', { name: 'Adicionar ao carrinho' }));
    await user.click(await screen.findByRole('link', { name: 'Ver carrinho' }));
    const summary = await screen.findByRole('complementary', { name: 'Resumo do carrinho' });
    let release!: () => void;
    server.controls.pause = new Promise<void>((resolve) => {
      release = resolve;
    });
    const quantity = screen.getByLabelText('Quantidade de Livro sintético');
    await user.clear(quantity);
    await user.type(quantity, '3');
    await user.click(screen.getByRole('button', { name: 'Atualizar quantidade' }));
    expect(summary).toHaveTextContent(/45,90/);
    expect(screen.getByRole('button', { name: 'Atualizar quantidade' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Remover Livro sintético' })).toBeDisabled();
    release();
    await waitFor(() => expect(summary).toHaveTextContent(/137,70/));
  });
  it('busca, filtra esgotados e abre detalhes com dados da API', async () => {
    const { server, user } = setup();
    expect(await screen.findByRole('link', { name: 'Livro sintético' })).toBeVisible();
    await user.type(screen.getByRole('searchbox', { name: 'Buscar por nome ou SKU' }), 'Caneca');
    await user.click(screen.getByRole('button', { name: 'Buscar' }));
    expect(await screen.findByRole('link', { name: 'Caneca sintética' })).toBeVisible();
    expect(screen.queryByRole('link', { name: 'Livro sintético' })).not.toBeInTheDocument();
    await user.clear(screen.getByRole('searchbox'));
    await user.selectOptions(screen.getByLabelText('Disponibilidade'), 'out');
    await user.click(screen.getByRole('button', { name: 'Buscar' }));
    const title = await screen.findByRole('link', {
      name: 'Produto sintético esgotado',
    });
    const card = title.closest('article')!;
    expect(within(card).getByRole('button', { name: 'Adicionar' })).toBeDisabled();
    await user.click(title);
    expect(
      await screen.findByRole('heading', { level: 1, name: 'Produto sintético esgotado' }),
    ).toBeVisible();
    expect(screen.getByRole('button', { name: 'Adicionar ao carrinho' })).toBeDisabled();
    expect(server.calls.some((call) => call.path.includes('in_stock=false'))).toBe(true);
  });

  it('adiciona, altera, remove e mantém os totais recebidos, sem preço enviado', async () => {
    const { server, user } = setup(`/catalogo/${BOOK}`);
    await screen.findByRole('heading', { level: 1, name: 'Livro sintético' });
    await user.clear(screen.getByLabelText('Quantidade'));
    await user.type(screen.getByLabelText('Quantidade'), '2');
    await user.click(screen.getByRole('button', { name: 'Adicionar ao carrinho' }));
    await user.click(await screen.findByRole('link', { name: 'Ver carrinho' }));
    const summary = await screen.findByRole('complementary', { name: 'Resumo do carrinho' });
    expect(summary).toHaveTextContent(/91,80/);
    expect(summary).toHaveTextContent('0,9 kg');
    const quantity = screen.getByLabelText('Quantidade de Livro sintético');
    await user.clear(quantity);
    await user.type(quantity, '3');
    expect(summary).toHaveTextContent(/91,80/); // draft is not an optimistic subtotal
    await user.click(screen.getByRole('button', { name: 'Atualizar quantidade' }));
    await waitFor(() => expect(summary).toHaveTextContent(/137,70/));
    expect(summary).toHaveTextContent('1,35 kg');
    await user.click(screen.getByRole('button', { name: 'Remover Livro sintético' }));
    expect(await screen.findByRole('heading', { name: 'Seu carrinho está vazio' })).toBeVisible();
    const edits = server.calls.filter((call) => call.path.includes('/items'));
    expect(edits.map((call) => call.method)).toEqual(['POST', 'PATCH', 'DELETE']);
    expect(
      edits.every(
        (call) =>
          !call.body ||
          Object.keys(call.body).every((key) =>
            ['expected_revision', 'product_id', 'quantity'].includes(key),
          ),
      ),
    ).toBe(true);
    expect(localStorage.getItem('freight-lab.cart-id')).toBe(server.cart().id);
    expect(localStorage.length).toBe(1);
  });

  it('aplica preço alterado no servidor em vez do preço visto anteriormente', async () => {
    const { server, user } = setup(`/catalogo/${BOOK}`);
    await screen.findByRole('heading', { level: 1, name: 'Livro sintético' });
    server.controls.reprice = 99;
    await user.click(screen.getByRole('button', { name: 'Adicionar ao carrinho' }));
    await user.click(await screen.findByRole('link', { name: 'Ver carrinho' }));
    expect(
      await screen.findByRole('complementary', { name: 'Resumo do carrinho' }),
    ).toHaveTextContent(/0,99/);
  });

  it('exibe estoque insuficiente e faz refetch, sem produto otimista no carrinho', async () => {
    const { server, user } = setup(`/catalogo/${BOOK}`);
    await screen.findByRole('heading', { level: 1, name: 'Livro sintético' });
    server.controls.failEdit = true;
    await user.click(screen.getByRole('button', { name: 'Adicionar ao carrinho' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Estoque insuficiente');
    expect(screen.queryByText('synthetic-private-detail-never-display')).not.toBeInTheDocument();
    expect(
      server.calls.some((call) => call.method === 'GET' && call.path.startsWith('/api/carts/')),
    ).toBe(true);
    expect(server.cart().items).toEqual([]);
  });

  it('não reaplica automaticamente operação em conflito e mostra dados atuais do servidor', async () => {
    const { server, user } = setup(`/catalogo/${BOOK}`);
    await screen.findByRole('heading', { level: 1, name: 'Livro sintético' });
    await user.click(screen.getByRole('button', { name: 'Adicionar ao carrinho' }));
    await user.click(await screen.findByRole('link', { name: 'Ver carrinho' }));
    await screen.findByRole('complementary', { name: 'Resumo do carrinho' });
    server.controls.conflict = true;
    const quantity = screen.getByLabelText('Quantidade de Livro sintético');
    await user.clear(quantity);
    await user.type(quantity, '3');
    await user.click(screen.getByRole('button', { name: 'Atualizar quantidade' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('carrinho mudou');
    await waitFor(() =>
      expect(screen.getByLabelText('Quantidade de Livro sintético')).toHaveValue('4'),
    );
    expect(server.calls.filter((call) => call.method === 'PATCH')).toHaveLength(1);
    expect(screen.getByRole('complementary', { name: 'Resumo do carrinho' })).toHaveTextContent(
      /183,60/,
    );
  });

  it('trata falha de rede e recupera catálogo sem exibir mensagem privada', async () => {
    const server = syntheticServer();
    server.controls.failProducts = true;
    vi.stubGlobal('fetch', vi.fn(server.fetcher));
    const client = createQueryClient();
    clients.push(client);
    render(
      <QueryClientProvider client={client}>
        <MemoryRouter initialEntries={['/catalogo']}>
          <App />
        </MemoryRouter>
      </QueryClientProvider>,
    );
    expect(await screen.findByRole('alert')).toHaveTextContent('Não foi possível conectar');
    expect(screen.queryByText('synthetic-private-network-error')).not.toBeInTheDocument();
    server.controls.failProducts = false;
    await userEvent.click(screen.getByRole('button', { name: 'Tentar novamente' }));
    expect(await screen.findByRole('link', { name: 'Livro sintético' })).toBeVisible();
  });
});
