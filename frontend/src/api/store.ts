import { z } from 'zod';
import { ApiError, requestInternal } from './http';

const integer = z.number().int().min(0).max(Number.MAX_SAFE_INTEGER);
export const productSchema = z.object({
  id: z.uuid(),
  sku: z.string(),
  name: z.string(),
  price_cents: integer,
  weight_grams: integer.min(1),
  length_cm: integer.min(1).max(300),
  width_cm: integer.min(1).max(300),
  height_cm: integer.min(1).max(300),
  stock_available: integer,
  status: z.enum(['active', 'inactive']),
});
export type Product = z.infer<typeof productSchema>;
const productPageSchema = z.object({
  items: z.array(productSchema),
  total: integer,
  page: integer.min(1),
  page_size: integer.min(1).max(100),
  total_pages: integer,
});

const cartItemSchema = z.object({
  id: z.uuid(),
  product_id: z.uuid(),
  sku: z.string(),
  name: z.string(),
  quantity: integer.min(1),
  unit_price_cents: integer,
  line_total_cents: integer,
  weight_grams: integer.min(1),
  line_weight_grams: integer.min(1),
  length_cm: integer.min(1),
  width_cm: integer.min(1),
  height_cm: integer.min(1),
  available_quantity: integer,
  problem: z.enum(['inactive_product', 'inventory_unavailable', 'insufficient_stock']).nullable(),
});
const cartSchema = z
  .object({
    id: z.uuid(),
    status: z.enum(['active', 'checkout_pending', 'checked_out', 'abandoned']),
    revision: integer.min(1),
    delivery_address: z.record(z.string(), z.json()).nullable(),
    items: z.array(cartItemSchema),
    subtotal_cents: integer,
    total_weight_grams: integer,
    total_quantity: integer,
    editable: z.boolean(),
    checkout_ready: z.boolean(),
    has_current_quote: z.boolean(),
  })
  .refine(
    (cart) =>
      cart.items.every(
        (item) =>
          item.line_total_cents === item.unit_price_cents * item.quantity &&
          item.line_weight_grams === item.weight_grams * item.quantity,
      ) &&
      cart.subtotal_cents === cart.items.reduce((sum, item) => sum + item.line_total_cents, 0) &&
      cart.total_weight_grams ===
        cart.items.reduce((sum, item) => sum + item.line_weight_grams, 0) &&
      cart.total_quantity === cart.items.reduce((sum, item) => sum + item.quantity, 0),
    'Totais recebidos não correspondem às linhas do servidor',
  );
export type Cart = z.infer<typeof cartSchema>;
export type CartItem = z.infer<typeof cartItemSchema>;
export interface CatalogFilter {
  page: number;
  q: string;
  stock: 'all' | 'available' | 'out';
}

export function getProducts(filter: CatalogFilter, signal?: AbortSignal) {
  const params = new URLSearchParams({ page: String(filter.page), page_size: '6' });
  if (filter.q) params.set('q', filter.q);
  if (filter.stock !== 'all') params.set('in_stock', String(filter.stock === 'available'));
  return requestInternal(`/api/products?${params}`, productPageSchema, { signal });
}
export async function getProduct(id: string, signal?: AbortSignal) {
  const result = await requestInternal(
    `/api/products/${encodeURIComponent(z.uuid().parse(id))}`,
    productSchema,
    {
      signal,
    },
  );
  if (result.id !== id)
    throw new ApiError('invalid-response', 'A resposta da API local não pôde ser validada.');
  return result;
}
export async function getCart(id: string, signal?: AbortSignal) {
  const result = await requestInternal(`/api/carts/${z.uuid().parse(id)}`, cartSchema, { signal });
  if (result.id !== id)
    throw new ApiError('invalid-response', 'A resposta da API local não pôde ser validada.');
  return result;
}
export function createCart() {
  return requestInternal('/api/carts', cartSchema, { method: 'POST', body: {} });
}
export function addItem(cart: Cart, productId: string, quantity: number) {
  return requestInternal(`/api/carts/${cart.id}/items`, cartSchema, {
    method: 'POST',
    body: {
      expected_revision: cart.revision,
      product_id: productId,
      quantity,
    },
  });
}
export function setQuantity(cart: Cart, itemId: string, quantity: number) {
  return requestInternal(`/api/carts/${cart.id}/items/${z.uuid().parse(itemId)}`, cartSchema, {
    method: 'PATCH',
    body: {
      expected_revision: cart.revision,
      quantity,
    },
  });
}
export function removeItem(cart: Cart, itemId: string) {
  return requestInternal(
    `/api/carts/${cart.id}/items/${z.uuid().parse(itemId)}?expected_revision=${cart.revision}`,
    cartSchema,
    { method: 'DELETE' },
  );
}
