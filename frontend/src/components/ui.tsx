import type { ButtonHTMLAttributes, ReactNode } from 'react';
import { BoxIcon } from './icons';

export function Button({
  className = '',
  children,
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button className={`button ${className}`} {...props}>
      {children}
    </button>
  );
}

export function PageHeading({
  eyebrow,
  title,
  children,
}: {
  eyebrow: string;
  title: string;
  children: ReactNode;
}) {
  return (
    <div className="page-heading">
      <p className="eyebrow">{eyebrow}</p>
      <h1 id="page-title" tabIndex={-1}>
        {title}
      </h1>
      <p className="page-description">{children}</p>
    </div>
  );
}

export function EmptyState({
  title,
  children,
  action,
}: {
  title: string;
  children: ReactNode;
  action?: ReactNode;
}) {
  return (
    <section className="state-panel empty-state">
      <span className="state-icon">
        <BoxIcon />
      </span>
      <h2>{title}</h2>
      <p>{children}</p>
      {action && <div className="state-action">{action}</div>}
    </section>
  );
}

export function LoadingState({ label = 'Carregando dados locais…' }: { label?: string }) {
  return (
    <div className="state-panel loading-state" role="status" aria-live="polite">
      <span className="spinner" aria-hidden="true" />
      <p>{label}</p>
      <div className="skeleton" aria-hidden="true" />
      <div className="skeleton short" aria-hidden="true" />
    </div>
  );
}

export function ErrorState({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <div className="state-panel error-state" role="alert">
      <span className="error-mark" aria-hidden="true">
        !
      </span>
      <h2>Não foi possível carregar</h2>
      <p>{message}</p>
      <Button onClick={onRetry}>Tentar novamente</Button>
    </div>
  );
}
