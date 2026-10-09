import { useQuery } from '@tanstack/react-query';
import { Link, useParams } from 'react-router-dom';
import { z } from 'zod';
import { ApiError } from '../api/http';
import { getProduct } from '../api/store';
import { useCartActions, useCartBusy } from '../cart/queries';
import { money, weight } from '../lib/format';
import { BoxIcon } from '../components/icons';
import QuantityForm from '../components/QuantityForm';
import { EmptyState, ErrorState, LoadingState, PageHeading } from '../components/ui';

export default function ProductPage() {
  const { productId = '' } = useParams();
  const valid = z.uuid().safeParse(productId).success;
  const product = useQuery({
    queryKey: ['product', productId],
    enabled: valid,
    queryFn: ({ signal }) => getProduct(productId, signal),
  });
  const edit = useCartActions();
  const busy = useCartBusy();
  if (!valid || (product.error instanceof ApiError && product.error.status === 404))
    return (
      <>
        <PageHeading eyebrow="Catálogo" title="Produto não encontrado">
          Este produto não está disponível na vitrine.
        </PageHeading>
        <EmptyState
          title="Escolha outro produto"
          action={
            <Link className="button" to="/catalogo">
              Voltar ao catálogo
            </Link>
          }
        >
          Produtos inativos não podem ser adicionados ao carrinho.
        </EmptyState>
      </>
    );
  if (product.isPending)
    return (
      <>
        <PageHeading eyebrow="Catálogo" title="Detalhes do produto">
          Buscando valores no servidor.
        </PageHeading>
        <LoadingState />
      </>
    );
  if (product.isError)
    return (
      <>
        <PageHeading eyebrow="Catálogo" title="Detalhes do produto">
          Confira a conexão local.
        </PageHeading>
        <ErrorState
          message={
            product.error instanceof ApiError
              ? product.error.message
              : 'Não foi possível carregar o produto.'
          }
          onRetry={() => {
            void product.refetch();
          }}
        />
      </>
    );
  const value = product.data;
  const available = value.status === 'active' && value.stock_available > 0;
  return (
    <>
      <Link className="back-link" to="/catalogo">
        ← Voltar ao catálogo
      </Link>
      <div className="product-detail-grid">
        <div className="product-detail-art" aria-hidden="true">
          <BoxIcon />
          <span>{value.sku}</span>
        </div>
        <section>
          <PageHeading eyebrow={value.sku} title={value.name}>
            Preço e medidas consultados na API da loja.
          </PageHeading>
          <span className={`stock-pill ${available ? '' : 'out'}`}>
            {available ? `${value.stock_available} disponíveis` : 'Esgotado'}
          </span>
          <p className="detail-price">{money(value.price_cents)}</p>
          <dl className="product-specs">
            <dt>Peso unitário</dt>
            <dd>{weight(value.weight_grams)}</dd>
            <dt>Dimensões</dt>
            <dd>
              {value.length_cm} × {value.width_cm} × {value.height_cm} cm
            </dd>
          </dl>
          <QuantityForm
            label="Quantidade"
            max={Math.min(1000, value.stock_available)}
            disabled={!available || busy}
            action={edit.isPending ? 'Adicionando…' : 'Adicionar ao carrinho'}
            onSubmit={(quantity) => edit.mutate({ kind: 'add', productId: value.id, quantity })}
          />
          {edit.isError && (
            <p role="alert" className="field-error">
              {edit.error instanceof ApiError ? edit.error.message : 'Não foi possível adicionar.'}
            </p>
          )}
          {edit.isSuccess && (
            <p role="status" className="added-message">
              Adicionado com os valores conferidos no servidor.{' '}
              <Link to="/carrinho">Ver carrinho</Link>
            </p>
          )}
          <p className="inline-note">
            Disponibilidade é momentânea. Adicionar não reserva estoque.
          </p>
        </section>
      </div>
    </>
  );
}
