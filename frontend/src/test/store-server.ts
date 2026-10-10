/** Explicitly synthetic local API fixture, not Packsenvios or a production pricing rule. */
import type { Cart, Product } from '../api/store';

export const BOOK = '00000000-0000-4000-8000-000000000010';
export const MUG = '00000000-0000-4000-8000-000000000011';
export const OUT = '00000000-0000-4000-8000-000000000012';
export const CART = '00000000-0000-4000-8000-000000000100';
export const PRODUCTS: Product[] = [
  {
    id: BOOK,
    sku: 'SYNTHETIC-BOOK',
    name: 'Livro sintético',
    price_cents: 4590,
    weight_grams: 450,
    length_cm: 23,
    width_cm: 16,
    height_cm: 3,
    stock_available: 12,
    status: 'active',
  },
  {
    id: MUG,
    sku: 'SYNTHETIC-MUG',
    name: 'Caneca sintética',
    price_cents: 3490,
    weight_grams: 360,
    length_cm: 12,
    width_cm: 12,
    height_cm: 10,
    stock_available: 7,
    status: 'active',
  },
  {
    id: OUT,
    sku: 'SYNTHETIC-OUT',
    name: 'Produto sintético esgotado',
    price_cents: 4990,
    weight_grams: 500,
    length_cm: 22,
    width_cm: 14,
    height_cm: 8,
    stock_available: 0,
    status: 'active',
  },
];

export function syntheticServer() {
  const products = structuredClone(PRODUCTS);
  const lines: { id: string; product: Product; quantity: number }[] = [];
  let revision = 1;
  let exists = false;
  let nextLine = 1;
  const calls: { path: string; method: string; body: Record<string, unknown> | null }[] = [];
  const controls: {
    failProducts: boolean;
    failEdit: boolean;
    conflict: boolean;
    reprice: number | null;
    pause: Promise<void> | null;
  } = { failProducts: false, failEdit: false, conflict: false, reprice: null, pause: null };

  const cart = (): Cart => ({
    id: CART,
    buyer_details: null,
    status: 'active',
    revision,
    delivery_address: null,
    items: lines.map((line) => ({
      id: line.id,
      product_id: line.product.id,
      sku: line.product.sku,
      name: line.product.name,
      quantity: line.quantity,
      unit_price_cents: line.product.price_cents,
      line_total_cents: line.product.price_cents * line.quantity,
      weight_grams: line.product.weight_grams,
      line_weight_grams: line.product.weight_grams * line.quantity,
      length_cm: line.product.length_cm,
      width_cm: line.product.width_cm,
      height_cm: line.product.height_cm,
      available_quantity: line.product.stock_available,
      problem: null,
    })),
    subtotal_cents: lines.reduce((sum, line) => sum + line.product.price_cents * line.quantity, 0),
    total_weight_grams: lines.reduce(
      (sum, line) => sum + line.product.weight_grams * line.quantity,
      0,
    ),
    total_quantity: lines.reduce((sum, line) => sum + line.quantity, 0),
    editable: true,
    checkout_ready: false,
    has_current_quote: false,
  });
  const response = (data: unknown, status = 200) =>
    new Response(JSON.stringify(data), { status, headers: { 'Content-Type': 'application/json' } });
  const error = (code: string, status = 409) =>
    response({ detail: { code, message: 'synthetic-private-detail-never-display' } }, status);

  async function fetcher(path: string, options: RequestInit = {}) {
    const method = options.method ?? 'GET';
    const body = options.body
      ? (JSON.parse(String(options.body)) as Record<string, unknown>)
      : null;
    calls.push({ path, method, body });
    const url = new URL(path, 'http://local.test');
    if (url.pathname === '/api/health')
      return response({ status: 'ok', service: 'freight-ecommerce-test' });
    if (url.pathname === '/api/runtime')
      return response({ freight_mode: 'mock', purchases_simulated: true });
    if (url.pathname === '/api/products') {
      if (controls.failProducts) throw new Error('synthetic-private-network-error');
      const q = (url.searchParams.get('q') ?? '').toLocaleLowerCase();
      const inStock = url.searchParams.get('in_stock');
      const items = products.filter(
        (product) =>
          `${product.name} ${product.sku}`.toLocaleLowerCase().includes(q) &&
          (inStock === null || product.stock_available > 0 === (inStock === 'true')),
      );
      return response({
        items,
        total: items.length,
        page: 1,
        page_size: 6,
        total_pages: items.length ? 1 : 0,
      });
    }
    if (url.pathname.startsWith('/api/products/')) {
      const product = products.find((item) => item.id === url.pathname.split('/').at(-1));
      return product ? response(product) : error('product_not_found', 404);
    }
    if (url.pathname === '/api/carts' && method === 'POST') {
      exists = true;
      return response(cart(), 201);
    }
    if (url.pathname === `/api/carts/${CART}` && method === 'GET')
      return exists ? response(cart()) : error('cart_not_found', 404);
    if (url.pathname.startsWith(`/api/carts/${CART}/items`)) {
      if (controls.pause) await controls.pause;
      if (controls.failEdit) return error('insufficient_stock');
      if (controls.conflict) {
        controls.conflict = false;
        revision += 1;
        if (lines[0]) lines[0].quantity = 4;
        return error('cart_revision_conflict');
      }
      const expected =
        method === 'DELETE'
          ? Number(url.searchParams.get('expected_revision'))
          : body?.expected_revision;
      if (expected !== revision) return error('cart_revision_conflict');
      if (method === 'POST') {
        const product = products.find((item) => item.id === body?.product_id)!;
        if (controls.reprice !== null) {
          product.price_cents = controls.reprice;
          controls.reprice = null;
        }
        const existing = lines.find((line) => line.product.id === product.id);
        const quantity = Number(body?.quantity) + (existing?.quantity ?? 0);
        if (quantity > product.stock_available) return error('insufficient_stock');
        if (existing) existing.quantity = quantity;
        else
          lines.push({
            id: `00000000-0000-4000-8000-${String(nextLine++).padStart(12, '0')}`,
            product,
            quantity,
          });
      } else {
        const index = lines.findIndex((line) => line.id === url.pathname.split('/').at(-1));
        if (index === -1) return error('cart_item_not_found', 404);
        if (method === 'PATCH') lines[index].quantity = Number(body?.quantity);
        else lines.splice(index, 1);
      }
      revision += 1;
      return response(cart());
    }
    throw new Error(`Unsupported synthetic local route ${method} ${path}`);
  }
  return { fetcher, calls, controls, cart, products };
}
