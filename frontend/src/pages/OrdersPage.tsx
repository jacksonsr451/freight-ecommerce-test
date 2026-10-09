import { Link } from 'react-router-dom';
import { EmptyState, PageHeading } from '../components/ui';

export default function OrdersPage() {
  return (
    <>
      <PageHeading eyebrow="Histórico local" title="Seus pedidos de teste">
        Uma linha do tempo para acompanhar cada compra simulada, com origem explícita dos eventos.
      </PageHeading>
      <EmptyState
        title="Os pedidos simulados terão espaço aqui"
        action={
          <Link className="button button-secondary" to="/catalogo">
            Voltar ao catálogo
          </Link>
        }
      >
        A consulta ao histórico será conectada junto ao fechamento de pedidos. Esta tela não
        representa uma resposta do banco.
      </EmptyState>
    </>
  );
}
