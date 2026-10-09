import { useId, useRef, useState } from 'react';
import { z } from 'zod';
import { Button, PageHeading } from '../components/ui';

const postalSchema = z.object({
  postal_code: z
    .string()
    .trim()
    .regex(/^[0-9]{8}$/, 'Informe um CEP com 8 dígitos, sem hífen.'),
});

export default function CheckoutPage() {
  const fieldId = useId();
  const input = useRef<HTMLInputElement>(null);
  const [postalCode, setPostalCode] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [validated, setValidated] = useState(false);

  return (
    <>
      <PageHeading eyebrow="Antes de fechar" title="Checkout de teste">
        Endereço, frete e pagamento terão estados explícitos. Nenhuma cobrança real é realizada.
      </PageHeading>
      <div className="checkout-grid">
        <section className="surface-card">
          <div className="card-heading">
            <span className="step-circle">1</span>
            <h2>Destino da compra</h2>
          </div>
          <p>Valide o formato do CEP para conhecer a base do formulário.</p>
          <form
            noValidate
            onSubmit={(event) => {
              event.preventDefault();
              const result = postalSchema.safeParse({ postal_code: postalCode });
              if (!result.success) {
                setError(result.error.issues[0].message);
                setValidated(false);
                input.current?.focus();
              } else {
                setError(null);
                setValidated(true);
              }
            }}
          >
            <div className="form-field">
              <label htmlFor={fieldId}>CEP de destino</label>
              <input
                ref={input}
                id={fieldId}
                name="postal_code"
                type="text"
                inputMode="numeric"
                autoComplete="postal-code"
                placeholder="01001000"
                value={postalCode}
                aria-invalid={Boolean(error)}
                aria-describedby={`${fieldId}-help${error ? ` ${fieldId}-error` : ''}`}
                onChange={(event) => {
                  setPostalCode(event.target.value);
                  setError(null);
                  setValidated(false);
                }}
              />
              <p className="field-help" id={`${fieldId}-help`}>
                8 dígitos. Zeros iniciais são preservados.
              </p>
              {error && (
                <p className="field-error" id={`${fieldId}-error`} role="alert">
                  {error}
                </p>
              )}
            </div>
            <Button type="submit">Validar CEP</Button>
            {validated && (
              <p className="form-success" role="status">
                CEP validado localmente. Nenhuma cotação foi enviada.
              </p>
            )}
          </form>
        </section>
        <aside className="summary-card" aria-label="Etapas do checkout">
          <p className="eyebrow">Jornada local</p>
          <h2>O próximo passo fica claro.</h2>
          <ol>
            <li>
              <strong>Endereço</strong>
              <span>Validar destino e dados do comprador</span>
            </li>
            <li>
              <strong>Comparação de fretes</strong>
              <span>Ofertas, estimativas e condições manuais</span>
            </li>
            <li>
              <strong>Pagamento simulado</strong>
              <span>Registrar o resultado somente na loja</span>
            </li>
          </ol>
          <p className="summary-note">
            Este formulário valida apenas o formato. Cotação e fechamento serão conectados nas
            próximas etapas.
          </p>
        </aside>
      </div>
    </>
  );
}
