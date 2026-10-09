import { useId, useState } from 'react';
import { z } from 'zod';
import { Button } from './ui';

export default function QuantityForm({
  label,
  initial = 1,
  max = 1000,
  disabled = false,
  action,
  onSubmit,
}: {
  label: string;
  initial?: number;
  max?: number;
  disabled?: boolean;
  action: string;
  onSubmit: (quantity: number) => void;
}) {
  const id = useId();
  const [value, setValue] = useState(String(initial));
  const [error, setError] = useState<string | null>(null);
  return (
    <form
      className="quantity-form"
      noValidate
      onSubmit={(event) => {
        event.preventDefault();
        const parsed = z
          .string()
          .regex(/^[0-9]+$/)
          .transform(Number)
          .pipe(z.number().int().min(1).max(Math.min(1000, max)))
          .safeParse(value);
        if (!parsed.success) {
          setError(`Informe uma quantidade inteira de 1 a ${Math.min(1000, max)}.`);
          return;
        }
        setError(null);
        onSubmit(parsed.data);
      }}
    >
      <div className="quantity-control">
        <label htmlFor={id}>{label}</label>
        <input
          id={id}
          inputMode="numeric"
          type="text"
          value={value}
          disabled={disabled}
          aria-invalid={Boolean(error)}
          aria-describedby={error ? `${id}-error` : undefined}
          onChange={(event) => {
            setValue(event.target.value);
            setError(null);
          }}
        />
      </div>
      <Button type="submit" disabled={disabled}>
        {action}
      </Button>
      {error && (
        <p id={`${id}-error`} role="alert" className="field-error">
          {error}
        </p>
      )}
    </form>
  );
}
