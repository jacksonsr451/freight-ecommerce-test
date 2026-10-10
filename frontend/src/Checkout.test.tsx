import { QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, expect, it, vi } from 'vitest';
import App from './App';
import { createQueryClient } from './lib/query-client';
import { setCartReference } from './cart/reference';
import { syntheticServer, BOOK, CART } from './test/store-server';

const clients: ReturnType<typeof createQueryClient>[] = [];
afterEach(() => {
  clients.forEach((client) => client.clear());
  clients.length = 0;
});
const REF = '00000000-0000-4000-8000-000000000200';
const OPTION = '00000000-0000-4000-8000-000000000201';
const SECOND = '00000000-0000-4000-8000-000000000202';

async function setup(status = 'quoted', httpError?: number) {
  const server = syntheticServer();
  await server.fetcher('/api/carts', { method: 'POST', body: '{}' });
  await server.fetcher(`/api/carts/${CART}/items`, {
    method: 'POST',
    body: JSON.stringify({ expected_revision: 1, product_id: BOOK, quantity: 1 }),
  });
  let buyer: { name: string; email: string } | null = null;
  let address: Record<string, unknown> | null = null;
  let revision = 2;
  const calls: { path: string; method: string; body: Record<string, unknown> | null }[] = [];
  const current = () => ({
    ...server.cart(),
    revision,
    buyer_details: buyer,
    delivery_address: address,
  });
  let result = {
    quote_reference: REF,
    cart_revision: 3,
    status,
    mode: 'mock',
    weight_only: false,
    selected_option_reference: null as string | null,
    options:
      status === 'quoted'
        ? [
            {
              reference: OPTION,
              carrier_name: 'Transportadora sintética A',
              price_cents: 2590,
              deadline_days: 3,
              manual_only: true,
              demonstration_only: true,
              weight_only: false,
              manual_review_required: true,
            },
            {
              reference: SECOND,
              carrier_name: 'Transportadora sintética B',
              price_cents: 3500,
              deadline_days: 1,
              manual_only: true,
              demonstration_only: false,
              weight_only: false,
              manual_review_required: true,
            },
          ]
        : [],
  };
  const control: { delay: Promise<void> | null } = { delay: null };
  const response = (body: unknown, code = 200, headers = {}) =>
    new Response(JSON.stringify(body), { status: code, headers });
  vi.stubGlobal(
    'fetch',
    vi.fn(async (path: string, options: RequestInit = {}) => {
      const body = options.body ? JSON.parse(String(options.body)) : null;
      calls.push({ path, method: options.method ?? 'GET', body });
      if (path === `/api/carts/${CART}`) return response(current());
      if (path.endsWith('/checkout-details')) {
        const changed =
          JSON.stringify(address) !== JSON.stringify(body.address) ||
          JSON.stringify(buyer) !== JSON.stringify(body.buyer);
        buyer = body.buyer;
        address = body.address;
        if (changed) {
          revision += 1;
          result = {
            ...result,
            status: 'invalidated',
            options: [],
            selected_option_reference: null,
          };
        }
        return response(current());
      }
      if (path.endsWith('/freight-quotes') && options.method === 'POST') {
        if (control.delay) await control.delay;
        if (httpError)
          return response(
            {
              detail: {
                code: `freight_${httpError === 401 ? 'unauthorized' : httpError === 403 ? 'forbidden' : httpError === 422 ? 'validation_error' : httpError === 429 ? 'rate_limited' : 'unavailable'}`,
                message: 'synthetic-private-secret',
              },
            },
            httpError,
            httpError === 429 ? { 'Retry-After': '2' } : {},
          );
        result = {
          ...result,
          status,
          cart_revision: revision,
          weight_only: body.packing_mode === 'weight_only',
          options:
            status === 'quoted'
              ? [
                  {
                    reference: OPTION,
                    carrier_name: 'Transportadora sintética A',
                    price_cents: 2590,
                    deadline_days: 3,
                    manual_only: true,
                    demonstration_only: true,
                    weight_only: body.packing_mode === 'weight_only',
                    manual_review_required: true,
                  },
                  {
                    reference: SECOND,
                    carrier_name: 'Transportadora sintética B',
                    price_cents: 3500,
                    deadline_days: 1,
                    manual_only: true,
                    demonstration_only: false,
                    weight_only: body.packing_mode === 'weight_only',
                    manual_review_required: true,
                  },
                ]
              : [],
        };
        return response(result);
      }
      if (path.endsWith('/selection')) {
        result.selected_option_reference = body.option_reference;
        return response(result);
      }
      if (path.endsWith(`/${REF}`)) return response(result);
      return server.fetcher(path, options);
    }),
  );
  setCartReference(CART);
  const client = createQueryClient();
  clients.push(client);
  render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={['/checkout']}>
        <App />
      </MemoryRouter>
    </QueryClientProvider>,
  );
  await screen.findByRole('textbox', { name: 'Nome do comprador' });
  return { calls, control, user: userEvent.setup() };
}

async function fill(user: ReturnType<typeof userEvent.setup>) {
  for (const [name, value] of [
    ['Nome do comprador', 'Comprador sintético'],
    ['E-mail', 'buyer@example.com'],
    ['CEP de destino', '01001000'],
    ['Rua', 'Rua sintética'],
    ['Número', '1'],
    ['Bairro', 'Centro'],
    ['Cidade', 'São Paulo'],
  ]) {
    await user.type(screen.getByRole('textbox', { name }), value);
  }
  await user.selectOptions(screen.getByLabelText('UF'), 'SP');
}

it('valida comprador/endereço, compara e seleciona somente referência interna', async () => {
  const { user, calls } = await setup();
  await fill(user);
  await user.click(screen.getByRole('button', { name: 'Salvar dados e cotar' }));
  expect(await screen.findByText('Transportadora sintética A')).toBeVisible();
  expect(screen.getByText('Somente demonstração')).toBeVisible();
  expect(screen.getByText('3 dias conforme tabela')).toBeVisible();
  await user.click(screen.getByRole('button', { name: /Selecionar oferta 2/ }));
  expect(
    await screen.findByText(
      'Oferta selecionada somente na loja. Nenhuma contratação ou pagamento externo foi realizado.',
    ),
  ).toBeVisible();
  const write = calls.find((call) => call.path.endsWith('/selection'))!;
  expect(write.body).toEqual({ expected_revision: 3, option_reference: SECOND });
  expect(calls.filter((call) => call.path.endsWith('/freight-quotes'))[0].body).toEqual({
    expected_revision: 3,
    packing_mode: 'equal_volumes',
    refresh: false,
  });
  expect(calls.every((call) => call.path.startsWith('/api/'))).toBe(true);
});

it('recalcula ao mudar endereço e oculta seleção antiga até receber nova cotação', async () => {
  const { user, calls } = await setup();
  await fill(user);
  await user.click(screen.getByRole('button', { name: 'Salvar dados e cotar' }));
  await user.click(await screen.findByRole('button', { name: /Selecionar oferta 2/ }));
  expect(await screen.findByText(/Oferta selecionada somente na loja/)).toBeVisible();
  const initial = calls.filter((call) => call.path.endsWith('/freight-quotes')).length;
  const postal = screen.getByRole('textbox', { name: 'CEP de destino' });
  await user.clear(postal);
  await user.type(postal, '20040002');
  expect(screen.queryByRole('button', { name: /Selecionar oferta/ })).not.toBeInTheDocument();
  expect(screen.queryByText(/Oferta selecionada somente na loja/)).not.toBeInTheDocument();
  await user.click(screen.getByRole('button', { name: 'Salvar dados e cotar' }));
  expect(await screen.findByRole('button', { name: /Selecionar oferta 1/ })).toBeVisible();
  expect(calls.filter((call) => call.path.endsWith('/freight-quotes'))).toHaveLength(initial + 1);
  const address = calls.filter((call) => call.path.endsWith('/checkout-details')).at(-1)?.body
    ?.address as { postal_code?: string } | undefined;
  expect(address?.postal_code).toBe('20040002');
});

it.each(['unavailable', 'fiscal_review'])(
  'mostra %s sem frete zero ou oferta inventada',
  async (status) => {
    const { user } = await setup(status);
    await fill(user);
    await user.click(screen.getByRole('button', { name: 'Salvar dados e cotar' }));
    expect(
      await screen.findByRole('heading', {
        name: status === 'unavailable' ? 'Nenhuma oferta disponível' : 'Revisão fiscal necessária',
      }),
    ).toBeVisible();
    expect(screen.queryByRole('button', { name: /Selecionar oferta/ })).not.toBeInTheDocument();
    expect(screen.getByText('Não selecionado')).toBeVisible();
  },
);

it.each([401, 403, 422, 429, 503])(
  'trata erro %s sem expor mensagem privada ou repetir POST',
  async (code) => {
    const { user, calls } = await setup('quoted', code);
    await fill(user);
    await user.click(screen.getByRole('button', { name: 'Salvar dados e cotar' }));
    expect(await screen.findByRole('alert')).toBeVisible();
    expect(screen.queryByText('synthetic-private-secret')).not.toBeInTheDocument();
    expect(
      calls.filter((call) => call.method === 'POST' && call.path.endsWith('/freight-quotes')),
    ).toHaveLength(1);
    if (code === 429)
      expect(screen.getByRole('button', { name: 'Cotar novamente' })).toBeDisabled();
  },
);

it('mostra loading e oculta oferta selecionada assim que endereço vira draft', async () => {
  const { user, control } = await setup();
  await fill(user);
  let release!: () => void;
  control.delay = new Promise<void>((resolve) => {
    release = resolve;
  });
  await user.click(screen.getByRole('button', { name: 'Salvar dados e cotar' }));
  expect(await screen.findByText('Consultando fretes pelo backend…')).toBeVisible();
  release();
  await user.click(await screen.findByRole('button', { name: /Selecionar oferta 1/ }));
  await screen.findByText(
    'Oferta selecionada somente na loja. Nenhuma contratação ou pagamento externo foi realizado.',
  );
  await user.type(screen.getByRole('textbox', { name: 'Número' }), '2');
  expect(screen.queryByRole('button', { name: /Selecionar oferta/ })).not.toBeInTheDocument();
  expect(screen.getByText('Não selecionado')).toBeVisible();
  control.delay = null;
  await user.click(screen.getByRole('button', { name: 'Salvar dados e cotar' }));
  expect(await screen.findByRole('button', { name: /Selecionar oferta 1/ })).toBeVisible();
});

it('sinaliza weight_only e recusa seleção visual da estimativa', async () => {
  const { user } = await setup();
  await fill(user);
  await user.selectOptions(screen.getByLabelText('Forma de cotação'), 'weight_only');
  await user.click(screen.getByRole('button', { name: 'Salvar dados e cotar' }));
  expect(
    await screen.findByText(
      'Estimativa weight_only: sem cubagem completa e não selecionável para fechar pedido.',
    ),
  ).toBeVisible();
  expect(
    screen
      .getAllByRole('button', { name: /Selecionar oferta/ })
      .every((button) => button.hasAttribute('disabled')),
  ).toBe(true);
});

it('foco e erros de formulário impedem HTTP com comprador/CEP inválidos', async () => {
  const { user, calls } = await setup();
  await user.click(screen.getByRole('button', { name: 'Salvar dados e cotar' }));
  expect(screen.getByRole('textbox', { name: 'Nome do comprador' })).toHaveFocus();
  expect(screen.getAllByRole('alert').length).toBeGreaterThan(1);
  expect(calls.some((call) => call.path.endsWith('/checkout-details'))).toBe(false);
});
