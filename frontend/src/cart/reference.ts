import { useSyncExternalStore } from 'react';
import { z } from 'zod';

const key = 'freight-lab.cart-id';
const changed = 'freight-lab-cart-changed';
let memory: string | null = null;

export function readCartReference(): string | null {
  let value: string | null;
  try {
    value = localStorage.getItem(key);
  } catch {
    value = memory;
  }
  const parsed = z.uuid().safeParse(value);
  return parsed.success ? parsed.data : null;
}
export function setCartReference(id: string | null) {
  memory = id === null ? null : z.uuid().parse(id);
  try {
    if (memory) localStorage.setItem(key, memory);
    else localStorage.removeItem(key);
  } catch {
    /* In-memory fallback, never store credentials/totals. */
  }
  window.dispatchEvent(new Event(changed));
}
function subscribe(listener: () => void) {
  window.addEventListener(changed, listener);
  window.addEventListener('storage', listener);
  return () => {
    window.removeEventListener(changed, listener);
    window.removeEventListener('storage', listener);
  };
}
export function useCartReference() {
  return useSyncExternalStore(subscribe, readCartReference, () => null);
}
