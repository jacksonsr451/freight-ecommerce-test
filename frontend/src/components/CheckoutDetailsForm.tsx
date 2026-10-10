import { useEffect, useId, useRef, useState } from 'react';
import type { Cart } from '../api/store';
import { checkoutFieldsSchema } from '../api/checkout';
import type { CheckoutFields } from '../api/checkout';
import { ApiError } from '../api/http';
import { Button } from './ui';

const fields = [
  ['buyer_name', 'Nome do comprador', 'name'],
  ['buyer_email', 'E-mail', 'email'],
  ['postal_code', 'CEP de destino', 'postal-code'],
  ['street', 'Rua', 'address-line1'],
  ['number', 'Número', 'off'],
  ['complement', 'Complemento (opcional)', 'address-line2'],
  ['district', 'Bairro', 'off'],
  ['city', 'Cidade', 'address-level2'],
] as const;
const states = [
  'AC',
  'AL',
  'AP',
  'AM',
  'BA',
  'CE',
  'DF',
  'ES',
  'GO',
  'MA',
  'MT',
  'MS',
  'MG',
  'PA',
  'PB',
  'PR',
  'PE',
  'PI',
  'RJ',
  'RN',
  'RS',
  'RO',
  'RR',
  'SC',
  'SP',
  'SE',
  'TO',
];

export default function CheckoutDetailsForm({
  cart,
  saving,
  onSave,
  onSaved,
  onReload,
  onDirty,
  onStale,
}: {
  cart: Cart;
  saving: boolean;
  onSave: (data: CheckoutFields, expectedRevision: number) => Promise<Cart>;
  onSaved: (cart: Cart) => void;
  onReload: () => Promise<Cart>;
  onDirty: (dirty: boolean) => void;
  onStale: (stale: boolean) => void;
}) {
  const form = useRef<HTMLFormElement>(null);
  const [expectedRevision, setExpectedRevision] = useState(cart.revision);
  const [resetVersion, setResetVersion] = useState(0);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [dirty, setDirty] = useState(false);
  const stale = expectedRevision !== cart.revision;
  const saved = Boolean(cart.buyer_details && cart.delivery_address);
  const errorId = useId();

  useEffect(() => {
    onStale(stale);
  }, [onStale, stale]);

  async function reload() {
    const fresh = await onReload();
    setExpectedRevision(fresh.revision);
    setDirty(false);
    onDirty(false);
    setErrors({});
    setSubmitError(null);
    setResetVersion((version) => version + 1);
  }

  return (
    <section className="surface-card">
      <div className="card-heading">
        <span className="step-circle">1</span>
        <h2>Comprador e destino</h2>
      </div>
      <p>Dados locais para a compra simulada. Nenhum documento fiscal é inventado.</p>
      <form
        ref={form}
        key={`${cart.id}:${resetVersion}`}
        noValidate
        onChange={() => {
          setDirty(true);
          onDirty(true);
        }}
        onSubmit={async (event) => {
          event.preventDefault();
          setSubmitError(null);
          if (stale) {
            setSubmitError('O carrinho mudou. Recarregue os dados antes de continuar.');
            return;
          }
          const result = checkoutFieldsSchema.safeParse(
            Object.fromEntries(new FormData(event.currentTarget)),
          );
          if (!result.success) {
            const next: Record<string, string> = {};
            result.error.issues.forEach((issue) => {
              const key = String(issue.path[0]);
              next[key] ??= issue.message;
            });
            setErrors(next);
            form.current?.querySelector<HTMLElement>(`[name="${Object.keys(next)[0]}"]`)?.focus();
            return;
          }
          setErrors({});
          try {
            const updated = await onSave(result.data, expectedRevision);
            setExpectedRevision(updated.revision);
            setDirty(false);
            onDirty(false);
            onStale(false);
            onSaved(updated);
          } catch (error) {
            const message =
              error instanceof ApiError ? error.message : 'Não foi possível salvar o checkout.';
            setSubmitError(message);
            if (error instanceof ApiError && error.status === 409) await reload();
          }
        }}
      >
        <fieldset className="checkout-fields" disabled={saving}>
          <legend className="visually-hidden">Dados do comprador e endereço brasileiro</legend>
          {fields.map(([name, label, autocomplete]) => (
            <div className="form-field" key={name}>
              <label htmlFor={`checkout-${name}`}>{label}</label>
              <input
                id={`checkout-${name}`}
                name={name}
                autoComplete={autocomplete}
                type={name === 'buyer_email' ? 'email' : 'text'}
                inputMode={name === 'postal_code' ? 'numeric' : undefined}
                defaultValue={
                  name === 'buyer_name'
                    ? (cart.buyer_details?.name ?? '')
                    : name === 'buyer_email'
                      ? (cart.buyer_details?.email ?? '')
                      : String(cart.delivery_address?.[name] ?? '')
                }
                aria-invalid={Boolean(errors[name])}
                aria-describedby={
                  errors[name]
                    ? `${errorId}-${name}`
                    : name === 'postal_code'
                      ? 'postal-help'
                      : undefined
                }
              />
              {name === 'postal_code' && (
                <p id="postal-help" className="field-help">
                  8 dígitos, sem hífen. Zeros iniciais preservados.
                </p>
              )}
              {errors[name] && (
                <p role="alert" id={`${errorId}-${name}`} className="field-error">
                  {errors[name]}
                </p>
              )}
            </div>
          ))}
          <div className="form-field">
            <label htmlFor="checkout-state">UF</label>
            <select
              id="checkout-state"
              name="state"
              defaultValue={String(cart.delivery_address?.state ?? '')}
              aria-invalid={Boolean(errors.state)}
              aria-describedby={errors.state ? `${errorId}-state` : undefined}
            >
              <option value="">Selecione</option>
              {states.map((state) => (
                <option key={state}>{state}</option>
              ))}
            </select>
            {errors.state && (
              <p role="alert" id={`${errorId}-state`} className="field-error">
                {errors.state}
              </p>
            )}
          </div>
          <div className="checkout-submit">
            <Button type="submit">{saving ? 'Salvando dados…' : 'Salvar dados e cotar'}</Button>
          </div>
        </fieldset>
      </form>
      {submitError && (
        <p role="alert" className="cart-error">
          {submitError}
        </p>
      )}
      {stale && (
        <div role="alert" className="cart-error">
          <p>O carrinho mudou em outra operação. Revise os dados antes de continuar.</p>
          <Button
            className="button-secondary"
            disabled={saving}
            onClick={() => {
              void reload();
            }}
          >
            Recarregar dados do checkout
          </Button>
        </div>
      )}
      {dirty && saved && (
        <p className="notice">
          Há dados editados. Ofertas anteriores estão ocultas até salvar e recalcular.
        </p>
      )}
    </section>
  );
}
