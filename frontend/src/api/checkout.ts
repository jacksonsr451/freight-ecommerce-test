import { z } from 'zod';
import { requestInternal } from './http';
import { cartSchema } from './store';
import type { Cart } from './store';

export const checkoutFieldsSchema = z.object({
  buyer_name: z.string().trim().min(2, 'Informe o nome com ao menos 2 caracteres.').max(160),
  buyer_email: z.email('Informe um e-mail válido.').max(254),
  postal_code: z.string().regex(/^[0-9]{8}$/, 'Informe um CEP com 8 dígitos, sem hífen.'),
  street: z.string().trim().min(2, 'Informe a rua.').max(255),
  number: z.string().trim().min(1, 'Informe o número.').max(32),
  complement: z.string().trim().max(120),
  district: z.string().trim().min(2, 'Informe o bairro.').max(120),
  city: z.string().trim().min(2, 'Informe a cidade.').max(120),
  state: z.string().regex(/^[A-Z]{2}$/, 'Selecione uma UF.'),
});
export type CheckoutFields = z.infer<typeof checkoutFieldsSchema>;
const money = z.number().int().min(0).max(Number.MAX_SAFE_INTEGER);
const optionSchema = z.object({
  reference: z.uuid(),
  carrier_name: z.string().nullable(),
  price_cents: money,
  deadline_days: z.number().int().min(0).nullable(),
  manual_only: z.boolean().nullable(),
  demonstration_only: z.boolean().nullable(),
  weight_only: z.boolean(),
  manual_review_required: z.boolean(),
});
export const quoteSchema = z
  .object({
    quote_reference: z.uuid(),
    cart_revision: z.number().int().min(1),
    status: z.enum(['pending', 'quoted', 'unavailable', 'fiscal_review', 'failed', 'invalidated']),
    mode: z.enum(['mock', 'real']),
    weight_only: z.boolean(),
    options: z.array(optionSchema),
    selected_option_reference: z.uuid().nullable(),
  })
  .refine(
    (quote) =>
      quote.selected_option_reference === null ||
      quote.options.some((option) => option.reference === quote.selected_option_reference),
    'Seleção não pertence às opções recebidas',
  );
export type Quote = z.infer<typeof quoteSchema>;
export type PackingMode = 'equal_volumes' | 'weight_only';

export function saveCheckout(cart: Cart, fields: CheckoutFields) {
  return requestInternal(`/api/carts/${cart.id}/checkout-details`, cartSchema, {
    method: 'PUT',
    body: {
      expected_revision: cart.revision,
      buyer: { name: fields.buyer_name, email: fields.buyer_email },
      address: {
        postal_code: fields.postal_code,
        street: fields.street,
        number: fields.number,
        complement: fields.complement || null,
        district: fields.district,
        city: fields.city,
        state: fields.state,
        country: 'BR',
      },
    },
  });
}
export function createQuote(cart: Cart, packingMode: PackingMode, refresh = false) {
  return requestInternal(`/api/carts/${cart.id}/freight-quotes`, quoteSchema, {
    method: 'POST',
    body: {
      expected_revision: cart.revision,
      packing_mode: packingMode,
      refresh,
    },
  });
}
export function getQuote(cartId: string, reference: string, signal?: AbortSignal) {
  return requestInternal(
    `/api/carts/${z.uuid().parse(cartId)}/freight-quotes/${z.uuid().parse(reference)}`,
    quoteSchema,
    { signal },
  );
}
export function selectQuoteOption(cart: Cart, reference: string, option: string) {
  return requestInternal(
    `/api/carts/${cart.id}/freight-quotes/${z.uuid().parse(reference)}/selection`,
    quoteSchema,
    {
      method: 'POST',
      body: {
        expected_revision: cart.revision,
        option_reference: z.uuid().parse(option),
      },
    },
  );
}
