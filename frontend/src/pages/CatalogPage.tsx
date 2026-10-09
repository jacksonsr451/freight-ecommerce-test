import { useQuery } from '@tanstack/react-query';
import { Link, useSearchParams } from 'react-router-dom';
import { ApiError } from '../api/http';
import { getProducts } from '../api/store';
import type { CatalogFilter } from '../api/store';
import ProductCard from '../components/ProductCard';
import { ArrowIcon, BoxIcon, CheckIcon } from '../components/icons';
import { Button, EmptyState, ErrorState, LoadingState, PageHeading } from '../components/ui';

export default function CatalogPage() {
  const [params, setParams] = useSearchParams();
  const q = params.get('q') ?? '';
  const stock = params.get('stock');
  const pageValue = Number(params.get('page') ?? 1);
  const filter: CatalogFilter = {
    q: q.slice(0, 100),
    page: Number.isInteger(pageValue) && pageValue > 0 && pageValue <= 1_000_000 ? pageValue : 1,
    stock: stock === 'available' || stock === 'out' ? stock : 'all',
  };
  const products = useQuery({
    queryKey: ['products', filter],
    queryFn: ({ signal }) => getProducts(filter, signal),
  });
  const changePage = (page: number) => {
    const next = new URLSearchParams(params);
    next.set('page', String(page));
    setParams(next);
  };
  return (
    <>
      <section className="catalog-hero">
        <div>
          <PageHeading
            eyebrow="Vitrine de demonstração"
            title="Uma compra de teste. Tudo às claras."
          >
            Explore uma jornada local: produtos sintéticos, valores calculados no servidor e fretes
            com snapshots rastreáveis.
          </PageHeading>
          <Link className="button" to="/checkout">
            Conhecer o checkout <ArrowIcon />
          </Link>
          <p className="hero-note">
            <CheckIcon /> Sem cobrança ou contratação automática
          </p>
        </div>
        <div className="parcel-illustration" aria-hidden="true">
          <span className="parcel-line" />
          <div className="parcel-card">
            <BoxIcon />
            <span>ORIGEM → DESTINO</span>
            <strong>
              Dados de teste.
              <br />
              Decisões claras.
            </strong>
          </div>
          <div className="parcel-stamp">
            <CheckIcon /> LOCAL & SIMULADO
          </div>
        </div>
      </section>
      <div className="feature-grid">
        <article>
          <span className="feature-number">01</span>
          <h2>O servidor calcula</h2>
          <p>Preço, peso e estoque têm uma única fonte de verdade.</p>
        </article>
        <article>
          <span className="feature-number">02</span>
          <h2>Você compara</h2>
          <p>Preço, prazo e condições do frete aparecem com contexto.</p>
        </article>
        <article>
          <span className="feature-number">03</span>
          <h2>O teste é local</h2>
          <p>Compra e pagamento simulados, sem efeito financeiro real.</p>
        </article>
      </div>
      <div className="section-heading">
        <h2>Catálogo</h2>
        <span className="subtle-badge">
          {products.data ? `${products.data.total} produtos` : 'API local'}
        </span>
      </div>
      <form
        className="catalog-filters"
        key={`${q}:${stock}`}
        onSubmit={(event) => {
          event.preventDefault();
          const fields = new FormData(event.currentTarget);
          const next = new URLSearchParams();
          const search = String(fields.get('q') ?? '').trim();
          if (search) next.set('q', search);
          const available = String(fields.get('stock') ?? 'all');
          if (available !== 'all') next.set('stock', available);
          setParams(next);
        }}
      >
        <div>
          <label htmlFor="catalog-search">Buscar por nome ou SKU</label>
          <input
            id="catalog-search"
            name="q"
            type="search"
            maxLength={100}
            defaultValue={q}
            placeholder="Ex.: livro, caneca…"
          />
        </div>
        <div>
          <label htmlFor="catalog-stock">Disponibilidade</label>
          <select id="catalog-stock" name="stock" defaultValue={filter.stock}>
            <option value="all">Todos</option>
            <option value="available">Disponíveis</option>
            <option value="out">Esgotados</option>
          </select>
        </div>
        <Button type="submit">Buscar</Button>
      </form>
      {products.isPending ? (
        <LoadingState label="Carregando catálogo do servidor…" />
      ) : products.isError ? (
        <ErrorState
          message={
            products.error instanceof ApiError
              ? products.error.message
              : 'Não foi possível carregar o catálogo.'
          }
          onRetry={() => {
            void products.refetch();
          }}
        />
      ) : products.data.items.length === 0 ? (
        <EmptyState
          title="Nenhum produto disponível nesta busca"
          action={
            <Button className="button-secondary" onClick={() => setParams({})}>
              Limpar filtros
            </Button>
          }
        >
          Confira os filtros ou carregue os produtos sintéticos no banco local. Nenhum preço é
          gerado pela interface.
        </EmptyState>
      ) : (
        <>
          <div className="product-grid">
            {products.data.items.map((product) => (
              <ProductCard key={product.id} product={product} />
            ))}
          </div>
          <nav className="pagination" aria-label="Paginação do catálogo">
            <Button
              className="button-secondary"
              disabled={filter.page === 1}
              onClick={() => changePage(filter.page - 1)}
            >
              Página anterior
            </Button>
            <span>
              Página {products.data.page} de {products.data.total_pages}
            </span>
            <Button
              className="button-secondary"
              disabled={filter.page >= products.data.total_pages}
              onClick={() => changePage(filter.page + 1)}
            >
              Próxima página
            </Button>
          </nav>
        </>
      )}
    </>
  );
}
