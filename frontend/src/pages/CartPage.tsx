import { Link } from 'react-router-dom';
import { useQueryClient } from '@tanstack/react-query';
import { ApiError } from '../api/http';
import { cartKey, useCart, useCartActions, useCartBusy } from '../cart/queries';
import { setCartReference, useCartReference } from '../cart/reference';
import { money, weight } from '../lib/format';
import QuantityForm from '../components/QuantityForm';
import { Button, EmptyState, ErrorState, LoadingState, PageHeading } from '../components/ui';

export default function CartPage() {
  const id = useCartReference();
  const cart = useCart();
  const edit = useCartActions();
  const busy = useCartBusy();
  const client = useQueryClient();
  const reset = () => {
    setCartReference(null);
    client.removeQueries({ queryKey: cartKey(id) });
    edit.reset();
  };
  let content;
  if (!id)
    content = (
      <EmptyState
        title="Seu carrinho começa pelo catálogo"
        action={
          <Link className="button" to="/catalogo">
            Explorar catálogo
          </Link>
        }
      >
        Escolha um produto para criar seu carrinho persistido na loja.
      </EmptyState>
    );
  else if (cart.isPending) content = <LoadingState label="Conferindo carrinho no servidor…" />;
  else if (cart.isError)
    content = (
      <>
        <ErrorState
          message={
            cart.error instanceof ApiError
              ? cart.error.message
              : 'Não foi possível consultar o carrinho.'
          }
          onRetry={() => {
            void cart.refetch();
          }}
        />
        {cart.error instanceof ApiError && cart.error.status === 404 && (
          <Button className="button-secondary" onClick={reset}>
            Começar outro carrinho
          </Button>
        )}
      </>
    );
  else if (cart.data.items.length === 0)
    content = (
      <EmptyState
        title="Seu carrinho está vazio"
        action={
          <Link className="button" to="/catalogo">
            Explorar catálogo
          </Link>
        }
      >
        Itens removidos e totais conferidos no servidor. Escolha algo para continuar.
      </EmptyState>
    );
  else {
    const data = cart.data;
    const blocked = busy || cart.isFetching || !data.editable;
    content = (
      <div className="cart-layout">
        <div className="cart-lines">
          {!data.editable && (
            <p className="notice">
              Este carrinho está encerrado.{' '}
              <Button className="button-secondary" onClick={reset}>
                Começar outro carrinho
              </Button>
            </p>
          )}
          {edit.isError && (
            <p role="alert" className="cart-error">
              {edit.error instanceof ApiError
                ? edit.error.message
                : 'Não foi possível alterar o carrinho.'}
            </p>
          )}
          {data.items.map((item) => (
            <article className="cart-line" key={item.id}>
              <div>
                <p className="eyebrow">{item.sku}</p>
                <h2>
                  <Link to={`/catalogo/${item.product_id}`}>{item.name}</Link>
                </h2>
                <p className="product-measures">
                  {money(item.unit_price_cents)} / unidade · {weight(item.weight_grams)}
                </p>
                {item.problem && (
                  <p role="alert" className="field-error">
                    {item.problem === 'inactive_product'
                      ? 'Produto inativo.'
                      : item.problem === 'inventory_unavailable'
                        ? 'Inventário indisponível.'
                        : `Estoque insuficiente: ${item.available_quantity} disponíveis.`}
                  </p>
                )}
                <QuantityForm
                  key={`${item.id}:${data.revision}`}
                  label={`Quantidade de ${item.name}`}
                  initial={item.quantity}
                  disabled={
                    blocked ||
                    item.problem === 'inactive_product' ||
                    item.problem === 'inventory_unavailable'
                  }
                  action="Atualizar quantidade"
                  onSubmit={(quantity) =>
                    edit.mutate({ kind: 'quantity', itemId: item.id, quantity })
                  }
                />
                <Button
                  className="remove-button"
                  disabled={blocked}
                  aria-label={`Remover ${item.name}`}
                  onClick={() => edit.mutate({ kind: 'remove', itemId: item.id })}
                >
                  Remover
                </Button>
              </div>
              <div className="cart-line-total">
                <span>Total da linha</span>
                <strong>{money(item.line_total_cents)}</strong>
              </div>
            </article>
          ))}
        </div>
        <aside className="cart-summary" aria-label="Resumo do carrinho">
          <p className="eyebrow">Valores do servidor</p>
          <h2>Resumo da seleção</h2>
          <dl>
            <dt>Unidades</dt>
            <dd>{data.total_quantity}</dd>
            <dt>Peso total informativo</dt>
            <dd>{weight(data.total_weight_grams)}</dd>
            <dt>Subtotal dos produtos</dt>
            <dd className="subtotal-value">{money(data.subtotal_cents)}</dd>
          </dl>
          <p>Frete será comparado no checkout. Estoque ainda não reservado.</p>
          {data.editable && data.items.every((item) => item.problem === null) ? (
            <Link className="button" to="/checkout">
              Continuar para checkout
            </Link>
          ) : (
            <span className="field-error">Revise os itens antes de continuar.</span>
          )}
          <small>Revisão {data.revision} · nenhuma cobrança real</small>
        </aside>
      </div>
    );
  }
  return (
    <>
      <PageHeading eyebrow="Sua seleção" title="Carrinho de compras">
        Preços, peso e subtotal são recalculados pelo servidor. Alterações só são aplicadas após
        confirmação da API.
      </PageHeading>
      {content}
      <p className="inline-note">
        Adicionar ao carrinho não reserva estoque. A reserva acontece apenas na confirmação local do
        pedido.
      </p>
    </>
  );
}
