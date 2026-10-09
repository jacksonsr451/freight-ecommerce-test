import { Link } from 'react-router-dom';
import { ArrowIcon } from '../components/icons';
import { EmptyState, PageHeading } from '../components/ui';

export default function CartPage() {
  return (
    <>
      <PageHeading eyebrow="Sua seleção" title="Carrinho de compras">
        Itens, quantidades e totais serão conferidos pelo servidor antes de seguir.
      </PageHeading>
      <EmptyState
        title="Seu carrinho começa pelo catálogo"
        action={
          <Link className="button" to="/catalogo">
            Explorar catálogo <ArrowIcon />
          </Link>
        }
      >
        Esta é a base visual do carrinho. A conexão com itens persistidos será feita na etapa de
        catálogo e carrinho.
      </EmptyState>
      <p className="inline-note">
        Adicionar ao carrinho não reserva estoque. A reserva acontece apenas na confirmação local do
        pedido.
      </p>
    </>
  );
}
