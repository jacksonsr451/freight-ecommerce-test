import { expect, it, vi } from 'vitest';
import { getCart, getProduct } from './store';
import { BOOK, CART, PRODUCTS } from '../test/store-server';

it('não corrige nem publica subtotal incoerente retornado pelo servidor', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          id: CART,
          revision: 1,
          status: 'active',
          delivery_address: null,
          editable: true,
          checkout_ready: false,
          has_current_quote: false,
          items: [],
          subtotal_cents: 99,
          total_weight_grams: 0,
          total_quantity: 0,
        }),
      ),
    ),
  );
  await expect(getCart(CART)).rejects.toMatchObject({ code: 'invalid-response' });
});

it('recusa identidade diferente da referência consultada', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify(PRODUCTS[1]))));
  await expect(getProduct(BOOK)).rejects.toMatchObject({ code: 'invalid-response' });
});
