import { Link } from 'react-router-dom';
import type { Product } from '../api/store';
import { ApiError } from '../api/http';
import { useCartActions, useCartBusy } from '../cart/queries';
import { money, weight } from '../lib/format';
import QuantityForm from './QuantityForm';
import { BoxIcon } from './icons';

export default function ProductCard({ product }: { product: Product }) {
  const edit = useCartActions();
  const busy = useCartBusy();
  const available = product.status === 'active' && product.stock_available > 0;
  return (
    <article className="product-card">
      <Link
        to={`/catalogo/${product.id}`}
        className="product-art"
        aria-label={`Detalhes de ${product.name}`}
      >
        <BoxIcon />
        <span>{product.sku}</span>
      </Link>
      <div className="product-card-body">
        <span className={`stock-pill ${available ? '' : 'out'}`}>
          {available ? `${product.stock_available} disponíveis` : 'Esgotado'}
        </span>
        <h3>
          <Link to={`/catalogo/${product.id}`}>{product.name}</Link>
        </h3>
        <p className="product-price">{money(product.price_cents)}</p>
        <p className="product-measures">
          {weight(product.weight_grams)} · {product.length_cm} × {product.width_cm} ×{' '}
          {product.height_cm} cm
        </p>
        <QuantityForm
          label={`Quantidade para ${product.name}`}
          max={Math.min(1000, product.stock_available)}
          disabled={!available || busy}
          action={edit.isPending ? 'Adicionando…' : 'Adicionar'}
          onSubmit={(quantity) => edit.mutate({ kind: 'add', productId: product.id, quantity })}
        />
        {edit.isError && (
          <p role="alert" className="field-error">
            {edit.error instanceof ApiError
              ? edit.error.message
              : 'Não foi possível alterar o carrinho.'}
          </p>
        )}
        {edit.isSuccess && (
          <p role="status" className="added-message">
            Adicionado ao carrinho. <Link to="/carrinho">Ver carrinho</Link>
          </p>
        )}
      </div>
    </article>
  );
}
