import { useLayoutEffect, useRef, type ReactNode } from 'react';
import { Link } from 'react-router-dom';
import { Loader2 } from 'lucide-react';
import { useNavData } from '../nav/useNav';
import { tabsFor } from '../nav/navModel';
import Shell from '../stitch/Shell';
import SqlInfo from '../components/SqlInfo';
import type { Kaynaklar } from '../components/sqlInfo';
import './seo.css';

/** SEO & GEO ekranlarının ortak iskeleti: kanvas kabuğu (menü adresten etkin öğeyi bulur), başlık. `path` ekranın adresidir; menü artık onu okumaz.
 *  `k`: ekranın ana ucunun sorgu bilgisi; başlığın yanında «i» (bu ekranın bütün sorguları ve hesabı). */
export default function SeoLayout({ crumb, eyebrow, title, lead, actions, children, k }: {
  path: string;
  crumb: string;
  eyebrow: string;
  title: string;
  lead: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
  k?: Kaynaklar | null;
}) {
  const first = k ? Object.keys(k.fields ?? {})[0] : undefined;
  return (
    <Shell head={{ tenant: 'Timaş Yayınları', section: 'SEO & GEO', crumb, source: 'T-soft + Google', presence: 'timas.com.tr' }}>
      <main className="sg-main">
        <div className="sg-page">
          <header className="sg-heading">
            <div>
              <div className="sg-eyebrow">{eyebrow}</div>
              <h1>
                {title}
                <span>.</span>
                {k && (first || k.error) && (
                  <SqlInfo k={k} alan={first ?? ''} label={`${title}: bu ekranın sorguları`} className="ml-2 align-middle" />
                )}
              </h1>
              <p>{lead}</p>
            </div>
            {actions && <div className="sg-actions">{actions}</div>}
          </header>
          <SeoTabs />
          {children}
        </div>
      </main>
    </Shell>
  );
}

/** Grubun sekmeleri (menüde tek giriş, ekranlar burada): kişinin görebildiği kardeş ekranlar, etkin olan işaretli.
 *  Her sekme kendi adresidir; geri tuşu, yer imi ve yetki ekran başına aynen çalışır. */
function SeoTabs() {
  const nav = useNavData();
  const group = nav.active?.group;
  const activeId = nav.active?.item.id;
  const visible = group ? nav.groups.find((g) => g.id === group.id)?.items ?? [] : [];
  const tabs = tabsFor(visible, activeId);
  const ref = useRef<HTMLElement>(null);
  // Telefonda şerit yatay kayar; etkin sekme görünür alana alınır (anında, sayfa kaymadan).
  useLayoutEffect(() => {
    const el = ref.current?.querySelector<HTMLElement>('[aria-current="page"]');
    const bar = ref.current;
    if (el && bar) bar.scrollLeft = el.offsetLeft - (bar.clientWidth - el.offsetWidth) / 2;
  }, [activeId]);
  if (tabs.length === 0) return null;
  return (
    <nav ref={ref} className="sg-tabs" aria-label="Bu bölümün ekranları">
      {tabs.map((t) => (
        <Link key={t.id} to={t.to} className="sg-tab" aria-current={t.id === activeId ? 'page' : undefined} title={t.hint}>
          {t.tabLabel ?? t.label}
        </Link>
      ))}
    </nav>
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

/** Rakamın yanındaki «i» (SEO & GEO): uç cevabının bütün alanları aynı hesaba ve o istekteki okumalara bağlıdır;
 *  alan adı gerekmez, cevabın ilk alanıyla açılır. Tablo başlığında, kartta, bölüm başlığında kullanılır. */
export function SeoInfo({ k, label, className }: { k?: Kaynaklar | null; label: string; className?: string }) {
  const first = k ? Object.keys(k.fields ?? {})[0] : undefined;
  if (!k || (!first && !k.error)) return null;
  return <SqlInfo k={k} alan={first ?? ''} label={label} className={className} />;
}
