import { Link } from 'react-router-dom';
import { EmptyState, PageHeading } from '../components/ui';

export default function NotFoundPage() {
  return (
    <>
      <PageHeading eyebrow="Página não encontrada" title="Vamos voltar ao caminho certo?">
        Este endereço não faz parte da loja de teste.
      </PageHeading>
      <EmptyState
        title="Encontre sua próxima etapa"
        action={
          <Link className="button" to="/catalogo">
            Voltar ao catálogo
          </Link>
        }
      >
        Use a navegação para acessar as áreas disponíveis.
      </EmptyState>
    </>
  );
}
