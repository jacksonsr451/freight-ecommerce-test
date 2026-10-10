import { useEffect, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Link, useNavigate } from 'react-router-dom';
import { ApiError } from '../api/http';
import { getCart } from '../api/store';
import type { Cart } from '../api/store';
import { createQuote, getQuote, saveCheckout, selectQuoteOption } from '../api/checkout';
import { createLocalOrder } from '../api/orders';
import type { CheckoutFields, PackingMode, Quote } from '../api/checkout';
import { cartKey, useCart, useCartBusy } from '../cart/queries';
import { useCartReference } from '../cart/reference';
import { money, weight } from '../lib/format';
import { Button, EmptyState, ErrorState, LoadingState, PageHeading } from '../components/ui';
import CheckoutDetailsForm from '../components/CheckoutDetailsForm';

const quoteKey = (cartId: string | null, reference: string | null, revision: number | undefined) =>
  ['checkout-quote', cartId, reference, revision] as const;

function errorMessage(error: Error | null) {
  return error instanceof ApiError
    ? error.message
    : 'Não foi possível concluir esta operação local.';
}

function localSubmissionKey(cartId: string, revision: number): string {
  const storageKey = `freight-lab.order-submission.${cartId}.${revision}`;
  try {
    const existing = sessionStorage.getItem(storageKey);
    if (existing && /^[0-9a-f-]{36}$/i.test(existing)) return existing;
    const key = crypto.randomUUID();
    sessionStorage.setItem(storageKey, key);
    return key;
  } catch {
    return crypto.randomUUID();
  }
}

export default function CheckoutPage() {
  const id = useCartReference();
  const cart = useCart();
  const client = useQueryClient();
  const navigate = useNavigate();
  const cartBusy = useCartBusy();
  const [dirty, setDirty] = useState(false);
  const [detailsStale, setDetailsStale] = useState(false);
  const [packing, setPacking] = useState<PackingMode>('equal_volumes');
  const [reference, setReference] = useState<string | null>(null);
  const [requestedPacking, setRequestedPacking] = useState<PackingMode>('equal_volumes');
  const [deadline, setDeadline] = useState(0);
  const [now, setNow] = useState(() => Date.now());
  const remaining = Math.max(0, Math.ceil((deadline - now) / 1000));

  useEffect(() => {
    if (deadline <= Date.now()) return;
    const timer = window.setInterval(() => {
      const current = Date.now();
      setNow(current);
      if (current >= deadline) window.clearInterval(timer);
    }, 1000);
    return () => window.clearInterval(timer);
  }, [deadline]);

  const reconcile = async () => {
    await client.invalidateQueries({ queryKey: ['cart'] });
    await client.invalidateQueries({ queryKey: ['checkout-quote'] });
  };
  const retryWait = (error: Error) => {
    if (error instanceof ApiError && error.retryAfterSeconds !== undefined) {
      setNow(Date.now());
      setDeadline(Date.now() + error.retryAfterSeconds * 1000);
    }
  };
  const quoted = useQuery({
    queryKey: quoteKey(id, reference, cart.data?.revision),
    enabled: Boolean(id && reference && cart.data),
    retry: false,
    queryFn: ({ signal }) => getQuote(id!, reference!, signal),
  });

  const receive = (response: Quote, current: Cart, mode: PackingMode) => {
    setReference(response.quote_reference);
    setRequestedPacking(mode);
    client.setQueryData(
      quoteKey(current.id, response.quote_reference, response.cart_revision),
      response,
    );
    void client.invalidateQueries({ queryKey: cartKey(current.id) });
  };

  const calculate = useMutation({
    mutationKey: ['checkout-calculate'],
    retry: false,
    mutationFn: async (input: { cart: Cart; mode: PackingMode; refresh: boolean }) => {
      const latest = await client.fetchQuery({
        queryKey: cartKey(input.cart.id),
        queryFn: ({ signal }) => getCart(input.cart.id, signal),
        staleTime: 0,
      });
      if (latest.revision !== input.cart.revision) {
        throw new ApiError(
          'http',
          'O carrinho mudou. Recarregue antes de cotar.',
          409,
          'cart_revision_conflict',
        );
      }
      const result = await createQuote(latest, input.mode, input.refresh);
      return { result, cart: latest, mode: input.mode };
    },
    onSuccess: ({ result, cart: current, mode }) => receive(result, current, mode),
    onError: async (error) => {
      retryWait(error);
      await reconcile();
    },
  });

  const save = useMutation({
    mutationKey: ['cart-edit'],
    scope: { id: 'cart-write' },
    retry: false,
    mutationFn: async (input: { data: CheckoutFields; cart: Cart; expectedRevision: number }) => {
      const latest = await client.fetchQuery({
        queryKey: cartKey(input.cart.id),
        queryFn: ({ signal }) => getCart(input.cart.id, signal),
        staleTime: 0,
      });
      if (latest.revision !== input.expectedRevision || latest.revision !== input.cart.revision) {
        throw new ApiError(
          'http',
          'O carrinho mudou em outra operação. Recarregue o checkout.',
          409,
          'cart_revision_conflict',
        );
      }
      const updated = await saveCheckout(latest, input.data);
      client.setQueryData(cartKey(updated.id), updated);
      return updated;
    },
    onError: reconcile,
  });

  const selection = useMutation({
    mutationKey: ['checkout-selection'],
    retry: false,
    mutationFn: async (option: string) => {
      const latest = await client.fetchQuery({
        queryKey: cartKey(id),
        queryFn: ({ signal }) => getCart(id!, signal),
        staleTime: 0,
      });
      return { response: await selectQuoteOption(latest, reference!, option), current: latest };
    },
    onSuccess: ({ response, current }) => receive(response, current, packing),
    onError: reconcile,
  });

  const createOrder = useMutation({
    mutationKey: ['local-order-create'],
    retry: false,
    mutationFn: async (input: { cart: Cart; key: string }) => {
      const latest = await client.fetchQuery({
        queryKey: cartKey(input.cart.id),
        queryFn: ({ signal }) => getCart(input.cart.id, signal),
        staleTime: 0,
      });
      if (latest.revision !== input.cart.revision) {
        throw new ApiError(
          'http',
          'O carrinho mudou. Revise e atualize a cotação.',
          409,
          'cart_revision_conflict',
        );
      }
      return createLocalOrder(latest.id, latest.revision, input.key);
    },
    onSuccess: (order) => {
      try {
        sessionStorage.removeItem(`freight-lab.order-submission.${id}.${order.cart_revision}`);
      } catch {
        /* Optional storage. */
      }
      navigate(`/pedidos/${order.id}`);
    },
    onError: reconcile,
  });

  const blocked =
    cartBusy || save.isPending || calculate.isPending || selection.isPending || cart.isFetching;
  const current = cart.data;
  const saved = Boolean(current?.buyer_details && current.delivery_address);
  const view =
    !dirty &&
    !detailsStale &&
    requestedPacking === packing &&
    quoted.data?.cart_revision === current?.revision
      ? quoted.data
      : undefined;
  const selected = view?.options.find(
    (option) => option.reference === view.selected_option_reference,
  );
  const modeError = calculate.error ?? selection.error;

  let content;
  if (!id || (current && current.items.length === 0)) {
    content = (
      <EmptyState
        title="Escolha produtos antes de comparar fretes"
        action={
          <Link className="button" to="/catalogo">
            Explorar catálogo
          </Link>
        }
      >
        Checkout utiliza o carrinho persistido, sem criar itens ou valores fictícios.
      </EmptyState>
    );
  } else if (cart.isPending) {
    content = <LoadingState label="Conferindo carrinho para checkout…" />;
  } else if (cart.isError) {
    content = (
      <ErrorState
        message={errorMessage(cart.error)}
        onRetry={() => {
          void cart.refetch();
        }}
      />
    );
  } else if (!current?.editable || current.items.some((item) => item.problem !== null)) {
    content = (
      <EmptyState
        title="Revise o carrinho antes de continuar"
        action={
          <Link className="button" to="/carrinho">
            Revisar carrinho
          </Link>
        }
      >
        Há itens indisponíveis ou o carrinho está encerrado.
      </EmptyState>
    );
  } else {
    content = (
      <div className="checkout-grid checkout-live">
        <div>
          <CheckoutDetailsForm
            cart={current}
            saving={save.isPending || remaining > 0}
            onSave={(data, expectedRevision) =>
              save.mutateAsync({ data, cart: current, expectedRevision })
            }
            onDirty={setDirty}
            onStale={setDetailsStale}
            onReload={async () => {
              const latest = await client.fetchQuery({
                queryKey: cartKey(current.id),
                queryFn: ({ signal }) => getCart(current.id, signal),
                staleTime: 0,
                retry: false,
              });
              client.setQueryData(cartKey(latest.id), latest);
              return latest;
            }}
            onSaved={(updated) => {
              setReference(null);
              selection.reset();
              calculate.reset();
              calculate.mutate({ cart: updated, mode: packing, refresh: false });
            }}
          />
          <section className="surface-card quote-section">
            <div className="card-heading">
              <span className="step-circle">2</span>
              <h2>Comparar fretes</h2>
            </div>
            <div className="form-field">
              <label htmlFor="packing-mode">Forma de cotação</label>
              <select
                id="packing-mode"
                value={packing}
                disabled={blocked}
                onChange={(event) => {
                  setPacking(event.target.value as PackingMode);
                  setReference(null);
                  calculate.reset();
                  selection.reset();
                }}
              >
                <option value="equal_volumes">Volumes iguais (medidas do catálogo)</option>
                <option value="weight_only">Estimativa somente pelo peso</option>
              </select>
            </div>
            <p className="inline-note">
              Volumes diferentes exigem revisão da embalagem ou estimativa explícita. Não são
              inventadas dimensões agregadas.
            </p>
            <Button
              className="button-secondary"
              disabled={!saved || dirty || detailsStale || blocked || remaining > 0}
              onClick={() => {
                selection.reset();
                calculate.mutate({ cart: current, mode: packing, refresh: false });
              }}
            >
              Cotar novamente
            </Button>
            {saved && (
              <Button
                className="button-secondary quote-refresh"
                disabled={dirty || detailsStale || blocked || remaining > 0}
                onClick={() => {
                  selection.reset();
                  setReference(null);
                  calculate.mutate({ cart: current, mode: packing, refresh: true });
                }}
              >
                Atualizar tabelas / nova cotação
              </Button>
            )}
            {remaining > 0 && (
              <p role="status" className="notice">
                Aguarde {remaining} segundos antes de tentar novamente (Retry-After).
              </p>
            )}
            {calculate.isPending ? (
              <LoadingState label="Consultando fretes pelo backend…" />
            ) : modeError ? (
              <p role="alert" className="cart-error">
                {errorMessage(modeError)}
              </p>
            ) : null}
            {quoted.isFetching && reference && !calculate.isPending && (
              <p role="status">Verificando validade da cotação…</p>
            )}
            {!saved && <p className="notice">Salve comprador e endereço para consultar ofertas.</p>}
            {view?.status === 'unavailable' && (
              <EmptyState title="Nenhuma oferta disponível">
                Não há oferta utilizável para esses critérios. Revise destino ou tente uma nova
                cotação; nenhum frete zero foi criado.
              </EmptyState>
            )}
            {view?.status === 'fiscal_review' && (
              <EmptyState title="Revisão fiscal necessária">
                O provedor exige revisão. Nenhum documento, autorização fiscal ou preço foi
                inventado.
              </EmptyState>
            )}
            {view?.status === 'pending' && (
              <div className="notice" role="status">
                <p>Cotação pendente no backend, sem conclusão confirmada.</p>
                <Button
                  className="button-secondary"
                  onClick={() => {
                    void quoted.refetch();
                  }}
                >
                  Consultar tentativa pendente
                </Button>
              </div>
            )}
            {(view?.status === 'invalidated' ||
              view?.status === 'failed' ||
              (reference &&
                !view &&
                !dirty &&
                !calculate.isPending &&
                !modeError &&
                !quoted.isFetching)) && (
              <p className="notice">
                Carrinho, endereço ou critérios mudaram. Recalcule para obter novas referências
                válidas.
              </p>
            )}
            {quoted.isError && !calculate.isPending && (
              <p role="alert" className="cart-error">
                {errorMessage(quoted.error)}
              </p>
            )}
            {view?.status === 'quoted' && (
              <fieldset className="freight-options" disabled={blocked || quoted.isFetching}>
                <legend>
                  Ofertas recebidas · {view.mode === 'mock' ? 'Mock sintético' : 'API real'}
                </legend>
                {view.weight_only && (
                  <p role="status" className="notice">
                    Estimativa weight_only: sem cubagem completa e não selecionável para fechar
                    pedido.
                  </p>
                )}
                {view.options.map((option, index) => (
                  <div
                    className={`freight-option ${view.selected_option_reference === option.reference ? 'selected' : ''}`}
                    key={option.reference}
                  >
                    <span>
                      <strong>{option.carrier_name ?? 'Nome não informado pelo provedor'}</strong>
                      <span className="freight-deadline">
                        {option.deadline_days === null
                          ? 'Prazo não informado'
                          : `${option.deadline_days} dias conforme tabela`}
                      </span>
                      <span className="offer-flags">
                        {option.manual_only === true && (
                          <span className="subtle-badge">Operação manual</span>
                        )}
                        {option.demonstration_only === true && (
                          <span className="subtle-badge">Somente demonstração</span>
                        )}
                        {option.manual_only === null && (
                          <span className="subtle-badge">Condição manual não informada</span>
                        )}
                        {option.manual_review_required && (
                          <span className="field-help">
                            Escolha somente local; requer revisão operacional.
                          </span>
                        )}
                      </span>
                    </span>
                    <span className="freight-price">{money(option.price_cents)}</span>
                    <Button
                      className="button-secondary option-select"
                      type="button"
                      disabled={option.weight_only || selection.isPending || quoted.isFetching}
                      aria-pressed={view.selected_option_reference === option.reference}
                      onClick={() => selection.mutate(option.reference)}
                    >
                      {view.selected_option_reference === option.reference
                        ? 'Selecionada localmente'
                        : `Selecionar oferta ${index + 1}`}
                    </Button>
                  </div>
                ))}
                {selection.isPending && <p role="status">Salvando escolha local por snapshot…</p>}
                {selected && (
                  <p role="status" className="form-success">
                    Oferta selecionada somente na loja. Nenhuma contratação ou pagamento externo foi
                    realizado.
                  </p>
                )}
              </fieldset>
            )}
          </section>
          {selected && (
            <section className="surface-card order-create-panel" aria-label="Pedido local simulado">
              <p className="eyebrow">Compra exclusivamente local</p>
              <h2>Pronto para criar o pedido de teste?</h2>
              <p>
                Pagamento simulado pela loja. Esta ação não contrata frete nem envia pedido à
                Packsenvios.
              </p>
              {selected.manual_review_required && (
                <p className="notice">
                  Esta oferta exige operação manual; o pedido registra apenas o vínculo local ao
                  snapshot.
                </p>
              )}
              <Button
                disabled={
                  cartBusy ||
                  save.isPending ||
                  calculate.isPending ||
                  selection.isPending ||
                  quoted.isFetching ||
                  createOrder.isPending ||
                  !current.checkout_ready ||
                  dirty ||
                  detailsStale ||
                  selected.weight_only
                }
                onClick={() =>
                  createOrder.mutate({
                    cart: current,
                    key: localSubmissionKey(current.id, current.revision),
                  })
                }
              >
                {createOrder.isPending ? 'Criando pedido local…' : 'Criar pedido local simulado'}
              </Button>
              {createOrder.isError && (
                <p role="alert" className="cart-error">
                  {errorMessage(createOrder.error)} A chave idempotente desta revisão será
                  reutilizada ao tentar novamente.
                </p>
              )}
            </section>
          )}
        </div>
        <aside className="cart-summary" aria-label="Resumo do checkout">
          <p className="eyebrow">Compra simulada</p>
          <h2>Seu pedido em preparação</h2>
          <dl>
            <dt>Produtos</dt>
            <dd>{money(current.subtotal_cents)}</dd>
            <dt>Peso informativo</dt>
            <dd>{weight(current.total_weight_grams)}</dd>
            <dt>Frete</dt>
            <dd>{selected ? money(selected.price_cents) : 'Não selecionado'}</dd>
          </dl>
          <p>
            Prazo é o da tabela, sem promessa de dias úteis/calendário. Cotação não reserva estoque
            nem cria envio.
          </p>
          <Link to="/carrinho" className="back-link">
            Revisar itens do carrinho
          </Link>
          {selected && (
            <p className="notice">
              Próxima etapa: pagamento e pedido locais simulados (prompt 11).
            </p>
          )}
        </aside>
      </div>
    );
  }
  return (
    <>
      <PageHeading eyebrow="Antes de fechar" title="Checkout de teste">
        Comprador, endereço e comparação de ofertas com snapshots. Compra e pagamento permanecem
        locais e simulados.
      </PageHeading>
      {content}
    </>
  );
}
