import { useEffect, useState } from 'react';
import { getHealth } from './api/health';

type ConnectionState = 'loading' | 'connected' | 'error';

export default function App() {
  const [connection, setConnection] = useState<ConnectionState>('loading');
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    void getHealth(controller.signal).then(
      () => {
        if (!controller.signal.aborted) setConnection('connected');
      },
      () => {
        if (!controller.signal.aborted) setConnection('error');
      },
    );
    return () => controller.abort();
  }, [attempt]);

  return (
    <main>
      <span className="badge">Desenvolvimento local · Bootstrap 01</span>
      <h1>Freight Ecommerce Test</h1>
      <p>Base de desenvolvimento para uma loja com compras e pagamentos simulados.</p>
      <section aria-labelledby="connection-heading">
        <h2 id="connection-heading">Conexão com a API local</h2>
        <p role="status" aria-live="polite">
          {connection === 'loading' && 'Verificando conexão…'}
          {connection === 'connected' && 'API local conectada.'}
          {connection === 'error' &&
            'Não foi possível conectar. Inicie o backend e tente novamente.'}
        </p>
        {connection === 'error' && (
          <button
            type="button"
            onClick={() => {
              setConnection('loading');
              setAttempt((value) => value + 1);
            }}
          >
            Tentar novamente
          </button>
        )}
      </section>
      <p className="note">
        Integração de frete prevista para etapas posteriores. Esta verificação confirma apenas o
        processo da API local.
      </p>
    </main>
  );
}
