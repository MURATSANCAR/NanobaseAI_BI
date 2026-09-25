import type { ReactNode } from 'react';
import { Loader2 } from 'lucide-react';
import Shell from '../stitch/Shell';
import { seoRail } from '../stitch/screens';
import './seo.css';

/** SEO & GEO ekranlarının ortak iskeleti: kanvas kabuğu, modülün rayı, başlık. */
export default function SeoLayout({ path, crumb, eyebrow, title, lead, actions, children }: {
  path: string;
  crumb: string;
  eyebrow: string;
  title: string;
  lead: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
}) {
  return (
    <Shell head={{ tenant: 'Timaş Yayınları', section: 'SEO & GEO', crumb, source: 'T-soft + Google', presence: 'timas.com.tr' }} rail={seoRail(path)}>
      <main className="sg-main">
        <div className="sg-page">
          <header className="sg-heading">
            <div>
              <div className="sg-eyebrow">{eyebrow}</div>
              <h1>
                {title}
                <span>.</span>
              </h1>
              <p>{lead}</p>
            </div>
            {actions && <div className="sg-actions">{actions}</div>}
          </header>
          {children}
        </div>
      </main>
    </Shell>
  );
}

export function Loading({ text }: { text: string }) {
  return (
    <section className="sg-empty">
      <Loader2 className="animate-spin" size={22} aria-hidden />
      <p>{text}</p>
    </section>
  );
}

export function Failed({ error }: { error: unknown }) {
  return <p className="sg-banner err">{(error as Error)?.message || 'Beklenmeyen hata.'}</p>;
}
