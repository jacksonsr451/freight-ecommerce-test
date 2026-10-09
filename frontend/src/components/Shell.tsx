import { useEffect, useRef, useState } from 'react';
import { Link, NavLink, Outlet, useLocation } from 'react-router-dom';
import { useHealth, useRuntime } from '../lib/runtime-queries';
import { BoxIcon, MenuIcon } from './icons';

const navigation = [
  ['/catalogo', 'Catálogo'],
  ['/carrinho', 'Carrinho'],
  ['/checkout', 'Checkout'],
  ['/pedidos', 'Pedidos'],
  ['/diagnostico', 'Diagnóstico'],
] as const;

export default function Shell() {
  const [menuOpen, setMenuOpen] = useState(false);
  const menuButton = useRef<HTMLButtonElement>(null);
  const location = useLocation();
  const previousPath = useRef(location.pathname);
  const runtime = useRuntime();
  const health = useHealth();
  const modeLabel = runtime.isError
    ? 'Modo indisponível'
    : runtime.isPending
      ? 'Verificando modo…'
      : runtime.data.freight_mode === 'mock'
        ? 'Mock · cotação sintética'
        : 'Real · compra simulada';

  useEffect(() => {
    const title =
      navigation.find(([path]) => location.pathname.startsWith(path))?.[1] ??
      'Página não encontrada';
    document.title = `${title} · Freight Lab`;
    if (previousPath.current !== location.pathname) {
      previousPath.current = location.pathname;
      document.getElementById('page-title')?.focus();
      window.scrollTo({ top: 0, behavior: 'instant' });
    }
  }, [location.pathname]);

  useEffect(() => {
    if (!menuOpen) return;
    const close = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        setMenuOpen(false);
        menuButton.current?.focus();
      }
    };
    window.addEventListener('keydown', close);
    return () => window.removeEventListener('keydown', close);
  }, [menuOpen]);

  return (
    <div className="app-shell">
      <a className="skip-link" href="#main-content">
        Pular para o conteúdo
      </a>
      <div className="simulation-strip">
        <span>Ambiente de testes</span>
        <span>Compras e pagamentos sempre simulados</span>
      </div>
      <header className="site-header">
        <div className="header-inner">
          <Link className="brand" to="/catalogo" aria-label="Freight Lab · início">
            <span className="brand-symbol">
              <BoxIcon />
            </span>
            <span>
              freight<span className="brand-light">lab</span>
              <small>E-commerce de teste</small>
            </span>
          </Link>
          <div
            className={`mode-badge ${runtime.isPending || runtime.isError ? 'unknown' : runtime.data?.freight_mode === 'real' ? 'real' : 'mock'}`}
            role="status"
            aria-live="polite"
            aria-label="Modo da cotação"
          >
            <span className="mode-dot" />
            {modeLabel}
          </div>
          <button
            className="menu-toggle"
            type="button"
            ref={menuButton}
            aria-expanded={menuOpen}
            aria-controls="main-navigation"
            aria-label={menuOpen ? 'Fechar menu' : 'Abrir menu'}
            onClick={() => setMenuOpen((open) => !open)}
          >
            <MenuIcon />
          </button>
          <nav
            className={`site-nav ${menuOpen ? 'open' : ''}`}
            id="main-navigation"
            aria-label="Principal"
          >
            {navigation.map(([path, label]) => (
              <NavLink
                key={path}
                to={path}
                onClick={() => {
                  setMenuOpen(false);
                  if (location.pathname === path) document.getElementById('page-title')?.focus();
                }}
              >
                {label}
              </NavLink>
            ))}
          </nav>
        </div>
      </header>
      <main className="main-content" id="main-content" tabIndex={-1}>
        <Outlet />
      </main>
      <footer className="site-footer">
        <div>
          <strong>Freight Lab</strong>
          <span>Do catálogo ao frete, com origem em cada dado.</span>
        </div>
        <div role="status" aria-live="polite" aria-label="Conexão com a API">
          <Link to="/diagnostico" className="connection-link">
            <span className={`connection-dot ${health.isSuccess ? 'connected' : ''}`} />
            {health.isPending
              ? 'Verificando API local…'
              : health.isError
                ? 'API local indisponível'
                : 'API local conectada'}
          </Link>
        </div>
        <p>Cotação não representa contratação, pagamento ou envio real.</p>
      </footer>
    </div>
  );
}
