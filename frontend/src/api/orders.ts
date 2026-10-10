import { z } from 'zod';
import { requestInternal } from './http';

const integer = z.number().int().min(0).max(Number.MAX_SAFE_INTEGER);
const payment = z.object({
  id: z.uuid(),
  status: z.enum(['pending', 'approved', 'declined']),
  amount_cents: integer,
  simulation: z.literal(true),
});
const fulfillment = z.object({
  status: z.enum([
    'pago_simulado',
    'separando',
    'embalado',
    'pronto_para_importacao',
    'importacao_pendente',
    'expedido_simulado',
    'entregue_simulado',
    'cancelado',
  ]),
  tracking_source: z.literal('simulated'),
});
export const orderSchema = z.object({
  id: z.uuid(),
  status: z.enum(['payment_pending', 'paid_simulated', 'payment_declined', 'cancelled']),
  simulation: z.literal(true),
  created_at: z.iso.datetime({ offset: true }),
  cart_revision: z.number().int().positive(),
  subtotal_cents: integer,
  freight_cents: integer,
  total_cents: integer,
  selected_option_reference: z.uuid(),
  freight_review_required: z.boolean(),
  shipping_destination: z.object({ postal_code: z.string(), city: z.string(), state: z.string() }),
  items: z.array(
    z.object({
      product_id: z.uuid(),
      sku: z.string(),
      name: z.string(),
      quantity: z.number().int().positive(),
      unit_price_cents: integer,
      line_total_cents: integer,
      product_snapshot: z.record(z.string(), z.json()),
    }),
  ),
  payment,
  fulfillment: fulfillment.nullable(),
  cancellation_reason: z.enum(['payment_declined', 'operator_cancelled']).nullable().optional(),
});
export type LocalOrder = z.infer<typeof orderSchema>;
const orderListSchema = z.object({ items: z.array(orderSchema), total: integer });

export function createLocalOrder(cartId: string, expectedRevision: number, submissionKey: string) {
  return requestInternal(`/api/carts/${z.uuid().parse(cartId)}/orders`, orderSchema, {
    method: 'POST',
    body: { expected_revision: expectedRevision, submission_key: z.uuid().parse(submissionKey) },
  });
}
export function confirmLocalPayment(
  orderId: string,
  expectedRevision: number,
  outcome: 'approved' | 'declined' | 'pending',
) {
  return requestInternal(`/api/orders/${z.uuid().parse(orderId)}/confirm`, orderSchema, {
    method: 'POST',
    body: { expected_cart_revision: expectedRevision, outcome },
  });
}
export function cancelLocalOrder(orderId: string, expectedRevision: number) {
  return requestInternal(`/api/orders/${z.uuid().parse(orderId)}/cancel`, orderSchema, {
    method: 'POST',
    body: { expected_cart_revision: expectedRevision },
  });
}
export function getLocalOrder(orderId: string, signal?: AbortSignal) {
  return requestInternal(`/api/orders/${z.uuid().parse(orderId)}`, orderSchema, { signal });
}
export function listLocalOrders(cartId: string, page = 1, pageSize = 20, signal?: AbortSignal) {
  const params = new URLSearchParams({ page: String(page), page_size: String(pageSize) });
  return requestInternal(`/api/carts/${z.uuid().parse(cartId)}/orders?${params}`, orderListSchema, {
    signal,
  });
}
