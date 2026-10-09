import { useIsMutating, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import type { QueryClient } from '@tanstack/react-query';
import { ApiError } from '../api/http';
import * as store from '../api/store';
import { readCartReference, setCartReference, useCartReference } from './reference';

export const cartKey = (id: string | null) => ['cart', id] as const;
const readRetry = (failures: number, error: Error) =>
  failures < 1 && error instanceof ApiError && error.code === 'network';
type Edit =
  | { kind: 'add'; productId: string; quantity: number }
  | { kind: 'quantity'; itemId: string; quantity: number }
  | { kind: 'remove'; itemId: string };
let creation: Promise<store.Cart> | null = null;

async function freshCart(client: QueryClient): Promise<store.Cart> {
  let id = readCartReference();
  if (!id) {
    creation ??= store.createCart();
    let created: store.Cart;
    try {
      created = await creation;
    } finally {
      creation = null;
    }
    client.setQueryData(cartKey(created.id), created);
    setCartReference(created.id);
    id = created.id;
  }
  const reference = id;
  const current = await client.fetchQuery({
    queryKey: cartKey(reference),
    queryFn: ({ signal }) => store.getCart(reference, signal),
    staleTime: 0,
    retry: readRetry,
    retryDelay: 100,
  });
  if (!current.editable)
    throw new ApiError(
      'http',
      'Este carrinho está encerrado e não pode ser alterado.',
      409,
      'cart_locked',
    );
  return current;
}

export function useCart() {
  const id = useCartReference();
  return useQuery({
    queryKey: cartKey(id),
    enabled: id !== null,
    staleTime: 0,
    retry: readRetry,
    retryDelay: 100,
    queryFn: ({ signal }) => store.getCart(id!, signal),
  });
}
export function useCartBusy() {
  return useIsMutating({ mutationKey: ['cart-edit'] }) > 0;
}
export function useCartActions() {
  const client = useQueryClient();
  return useMutation({
    mutationKey: ['cart-edit'],
    scope: { id: 'cart-write' },
    retry: false,
    mutationFn: async (edit: Edit) => {
      const current = await freshCart(client);
      const receipt =
        edit.kind === 'add'
          ? await store.addItem(current, edit.productId, edit.quantity)
          : edit.kind === 'quantity'
            ? await store.setQuantity(current, edit.itemId, edit.quantity)
            : await store.removeItem(current, edit.itemId);
      if (receipt.id !== current.id || receipt.revision < current.revision) {
        throw new ApiError('invalid-response', 'A resposta da API local não pôde ser validada.');
      }
      return receipt;
    },
    onSuccess: (updated) => {
      client.setQueryData(cartKey(updated.id), updated); // authoritative receipt, not local price math
      void client.invalidateQueries({ queryKey: ['products'] });
      void client.invalidateQueries({ queryKey: ['product'] });
    },
    onError: async () => {
      const id = readCartReference();
      if (id) {
        try {
          await client.fetchQuery({
            queryKey: cartKey(id),
            queryFn: ({ signal }) => store.getCart(id, signal),
            staleTime: 0,
            retry: readRetry,
            retryDelay: 100,
          });
        } catch {
          /* Query error stays visible; don't manufacture totals or retry the mutation. */
        }
      }
      await client.invalidateQueries({ queryKey: ['products'] });
      await client.invalidateQueries({ queryKey: ['product'] });
    },
  });
}
