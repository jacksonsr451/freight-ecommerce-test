import { Link } from 'react-router-dom';
import { ArrowIcon, BoxIcon, CheckIcon } from '../components/icons';
import { EmptyState, PageHeading } from '../components/ui';

export default function CatalogPage() {
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
        <span className="subtle-badge">Base visual</span>
      </div>
      <EmptyState title="A vitrine está pronta para receber produtos">
        A conexão com o catálogo persistido entra na próxima etapa. Nenhum produto ou preço foi
        inventado nesta tela.
      </EmptyState>
    </>
  );
}
