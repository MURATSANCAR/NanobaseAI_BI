import type { ReactNode } from 'react';
import { useEffect, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Check, ChevronLeft, ChevronRight, CircleHelp, Copy, ExternalLink, Loader2, RefreshCw, Search, X } from 'lucide-react';
import { ENGINE_ENABLED } from '../engine';
import { RIGHTS_LABEL, call, dateTime, fmt, qs, type CrmRights } from './api';
import SeoLayout, { Failed, Loading, SeoInfo } from './SeoLayout';

type AuthorStatus = 'wikipedia' | 'wikidata' | 'yok' | 'belirsiz' | 'bekliyor';
type GbCheck = 'isbn' | 'rights' | 'status' | 'cover' | 'pdf';
type RunState = { running: boolean; phase: string | null; done: number; queue: number | null; startedAt: string | null; finishedAt: string | null; error: string | null };
type OrgCheck = { id: string; title: string; ok: boolean | null; detail: string };
type Wikidata = {
  id: string;
  url: string;
  label: string | null;
  description: string | null;
  website: string[];
  socials: Array<{ property: string; network: string; id: string; url: string }>;
  wikipedia: Partial<Record<'trwiki' | 'enwiki', string>>;
  inception: string | null;
};
type Overview = {
  organization: {
    checkedAt: string;
    wikidata: Wikidata | null;
    wikidataReason: string | null;
    site: Record<string, unknown> | null;
    siteOk: boolean;
    checks: OrgCheck[];
    sameAs: string[];
    jsonld: string;
  } | null;
  authors: { total: number; counts: Record<AuthorStatus, number>; labels: Record<AuthorStatus, string>; lastChecked: string | null };
  books: {
    isbn: { active: number; checked: number; complete: boolean; found: number; byPublisher: number; checkedAt: string } | null;
    googleBooks: { total: number; ready: number; missing: Record<GbCheck, number>; checks: Record<GbCheck, string> };
  };
  state: RunState;
  refreshDays: number;
};
type Author = {
  name: string;
  sales: number;
  books: number;
  titles: string[];
  status: AuthorStatus;
  label: string;
  wikidata: string | null;
  wikipedia: string | null;
  description: string | null;
  needs: string[];
  checkedAt: string | null;
  stale: boolean;
};
type GbRow = {
  id: string;
  name: string;
  author: string;
  image: string | null;
  url: string | null;
  sales: number;
  isbn: string | null;
  rights: CrmRights | null;
  statusFlag: string | null;
  previewPdf: string | null;
  ebookRight: boolean;
  inCrm: boolean;
  checks: Record<GbCheck, boolean>;
  missing: string[];
  ready: boolean;
};

const PAGE = 40;
const TABS = [
  { id: 'kurum', label: 'Kurum' },
  { id: 'yazarlar', label: 'Yazarlar' },
  { id: 'google-kitaplar', label: 'Google Kitaplar hazırlığı' },
] as const;
type Tab = (typeof TABS)[number]['id'];
const STATUS_ORDER: AuthorStatus[] = ['yok', 'belirsiz', 'wikidata', 'wikipedia', 'bekliyor'];
const STATUS_TONE: Record<AuthorStatus, 'good' | 'mid' | 'bad' | 'violet' | ''> = {
  wikipedia: 'good',
  wikidata: 'violet',
  yok: 'bad',
  belirsiz: 'mid',
  bekliyor: '',
};

const api = {
  overview: () => call<Overview>('entity'),
  authors: (p: { status?: string; q?: string; start: number; limit: number }) =>
    call<{ total: number; start: number; counts: Record<AuthorStatus, number>; items: Author[] }>(`entity/authors?${qs(p)}`),
  books: (p: { ready?: string; missing?: string; start: number; limit: number }) =>
    call<{ total: number; start: number; items: GbRow[]; summary: Overview['books']['googleBooks'] & { total: number } }>(`entity/google-books?${qs(p)}`),
  refresh: (force: boolean) => call<{ started: boolean }>(`entity/refresh?${qs({ force: force ? 'true' : undefined })}`, { method: 'POST' }),
};

/** Kimlik ve bilgi paneli: Google ve yapay zekâ Timaş’ı, yazarlarını ve kitaplarını hangi açık kayıtlardan tanır; eksik ne.
 *  Wikidata, Wikipedia, anasayfa ve CRM yalnız okunur. */
export default function SeoEntity() {
  const qc = useQueryClient();
  const [params, setParams] = useSearchParams();
  const tab = (TABS.some((t) => t.id === params.get('sekme')) ? params.get('sekme') : 'kurum') as Tab;
  const set = (k: string, v: string) => {
    const next = new URLSearchParams(params);
    if (v) next.set(k, v);
    else next.delete(k);
    if (k === 'sekme') next.delete('suzgec');
    setParams(next, { replace: true });
  };

  const overview = useQuery({
    queryKey: ['seo-entity'],
    queryFn: api.overview,
    enabled: ENGINE_ENABLED,
    retry: false,
    refetchInterval: (s) => (s.state.data?.state.running ? 10000 : false),
  });
  const refresh = useMutation({
    mutationFn: api.refresh,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['seo-entity'] }),
  });
  const o = overview.data;
  const running = !!o?.state.running;
  const phase = o?.state.phase;

  return (
    <SeoLayout k={overview.data?.kaynaklar}
      path="/seo-geo/kimlik"
      crumb="Kimlik ve bilgi paneli"
      eyebrow="SEO & GEO · kimlik"
      title="Kimlik ve bilgi paneli"
      lead={`Google’ın bilgi paneli ve yapay zekâ motorları bir yayınevini, yazarı ve kitabı Wikidata, Wikipedia ve sitedeki kurum şeması gibi açık kayıtlardan tanır. Bu ekran bu kayıtların durumunu ve eksiklerini gösterir; hiçbir yere yazmaz. Kayıtlara ${o?.refreshDays ?? 30} günde bir yeniden bakılır.`}
      actions={
        <button className="sg-button" onClick={() => refresh.mutate(false)} disabled={refresh.isPending || running}>
          {running ? <Loader2 size={16} className="animate-spin" aria-hidden /> : <RefreshCw size={16} aria-hidden />}
          {running ? `Bakılıyor${phase ? ` · ${phase}` : ''} ${o?.state.queue ? `${fmt(o.state.done)} / ${fmt(o.state.queue)}` : ''}` : 'Eskimişlere yeniden bak'}
        </button>
      }
    >
      {overview.isLoading && <Loading text="Kimlik kayıtları getiriliyor…" />}
      {overview.error && <Failed error={overview.error} />}
      {refresh.error && <Failed error={refresh.error} />}
      {o?.state.error && <p className="sg-banner err">Son tur yarıda kaldı: {o.state.error}</p>}

      {o && (
        <>
          <section className="sg-kpis" aria-label="Özet">
            <Kpi
              label="Kurum kontrolleri"
              value={o.organization ? `${o.organization.checks.filter((c) => c.ok).length} / ${o.organization.checks.length}` : '—'}
              note={o.organization ? `Son bakış ${dateTime(o.organization.checkedAt)}` : 'Henüz bakılmadı'} info={<SeoInfo k={overview.data?.kaynaklar} label="Kurum kontrolleri" />} />
            <Kpi label="Wikipedia’sı olan yazar" value={fmt(o.authors.counts.wikipedia)} note={`${fmt(o.authors.total)} yazar · yalnız Wikidata ${fmt(o.authors.counts.wikidata)}`} tone="good" info={<SeoInfo k={overview.data?.kaynaklar} label="Wikipedia’sı olan yazar" />} />
            <Kpi label="Kaydı olmayan yazar" value={fmt(o.authors.counts.yok)} note={`Belirsiz ${fmt(o.authors.counts.belirsiz)} · bakılmadı ${fmt(o.authors.counts.bekliyor)}`} tone={o.authors.counts.yok ? 'bad' : undefined} info={<SeoInfo k={overview.data?.kaynaklar} label="Kaydı olmayan yazar" />} />
            <Kpi
              label="Wikidata’da kitap"
              value={o.books.isbn ? fmt(o.books.isbn.found) : '—'}
              note={o.books.isbn ? `${fmt(o.books.isbn.active)} aktif ISBN içinde${o.books.isbn.complete ? '' : ` · ${fmt(o.books.isbn.checked)} tanesine bakıldı`}` : 'Henüz bakılmadı'} info={<SeoInfo k={overview.data?.kaynaklar} label="Wikidata’da kitap" />} />
            <Kpi label="Google Kitaplar’a hazır" value={fmt(o.books.googleBooks.ready)} note={`${fmt(o.books.googleBooks.total)} aktif kitap içinde`} tone="good" info={<SeoInfo k={overview.data?.kaynaklar} label="Google Kitaplar’a hazır" />} />
          </section>

          <div className="sg-filters" role="tablist" aria-label="Bölüm">
            {TABS.map((t) => (
              <button key={t.id} className="sg-filter" role="tab" aria-selected={tab === t.id} aria-pressed={tab === t.id} onClick={() => set('sekme', t.id)}>
                {t.label}
              </button>
            ))}
          </div>

          {tab === 'kurum' && <Organization o={o} onRefresh={() => refresh.mutate(true)} busy={running || refresh.isPending} />}
          {tab === 'yazarlar' && <Authors filter={params.get('suzgec') ?? ''} setFilter={(v) => set('suzgec', v)} />}
          {tab === 'google-kitaplar' && <GoogleBooks filter={params.get('suzgec') ?? ''} setFilter={(v) => set('suzgec', v)} />}
        </>
      )}
    </SeoLayout>
  );
}

function Organization({ o, onRefresh, busy }: { o: Overview; onRefresh: () => void; busy: boolean }) {
  const org = o.organization;
  const [copied, setCopied] = useState(false);
  if (!org) {
    return (
      <div className="sg-empty">
        <h2>Kurum kaydına henüz bakılmadı</h2>
        <p>Wikidata’daki Timaş Yayınları kaydı ve anasayfadaki kurum şeması okunur; birkaç saniye sürer.</p>
        <button className="sg-button" onClick={onRefresh} disabled={busy}>
          <RefreshCw size={16} aria-hidden /> Şimdi bak
        </button>
      </div>
    );
  }
  const wd = org.wikidata;
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(org.jsonld);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      setCopied(false);
    }
  };
  return (
    <div className="sg-grid">
      <section className="sg-card sg-span-6" aria-label="Denetim">
        <h2>Kurum kimliği denetimi</h2>
        <p className="sg-sub">Son bakış {dateTime(org.checkedAt)}.</p>
        <ul style={{ listStyle: 'none', margin: 0, padding: 0, display: 'grid', gap: 10 }}>
          {org.checks.map((c) => (
            <li key={c.id} style={{ display: 'grid', gridTemplateColumns: '22px minmax(0, 1fr)', gap: 8, alignItems: 'start' }}>
              <span aria-label={c.ok ? 'Geçti' : c.ok === false ? 'Eksik' : 'Bakılamadı'} style={{ color: c.ok ? '#0f7a51' : c.ok === false ? '#c2361b' : 'var(--sg-muted)', paddingTop: 1 }}>
                {c.ok ? <Check size={16} aria-hidden /> : c.ok === false ? <X size={16} aria-hidden /> : <CircleHelp size={16} aria-hidden />}
              </span>
              <span style={{ minWidth: 0 }}>
                <span style={{ fontSize: 13, fontWeight: 700, color: 'var(--sg-ink)' }}>{c.title}</span>
                <span style={{ display: 'block', fontSize: 12, color: 'var(--sg-muted)', overflowWrap: 'anywhere' }}>{c.detail}</span>
              </span>
            </li>
          ))}
        </ul>
        <button className="sg-button" style={{ marginTop: 14 }} onClick={onRefresh} disabled={busy}>
          <RefreshCw size={16} aria-hidden /> Şimdi yeniden bak
        </button>
      </section>
      <section className="sg-card sg-span-6" aria-label="Wikidata">
        <h2>Wikidata kaydı</h2>
        {wd ? (
          <dl className="sg-facts">
            <div>
              <dt>Kayıt</dt>
              <dd>
                <a href={wd.url} target="_blank" rel="noreferrer">
                  {wd.id} · {wd.label} <ExternalLink size={11} aria-hidden />
                </a>
              </dd>
            </div>
            <div>
              <dt>Açıklama</dt>
              <dd>{wd.description || '—'}</dd>
            </div>
            <div>
              <dt>Resmî site</dt>
              <dd>{wd.website.join(', ') || '—'}</dd>
            </div>
            <div>
              <dt>Kuruluş</dt>
              <dd>{wd.inception || '—'}</dd>
            </div>
            <div>
              <dt>Wikipedia</dt>
              <dd>
                {Object.entries(wd.wikipedia).length
                  ? Object.entries(wd.wikipedia).map(([k, u]) => (
                      <a key={k} href={u} target="_blank" rel="noreferrer" style={{ marginRight: 8 }}>
                        {k === 'trwiki' ? 'Türkçe' : 'İngilizce'} <ExternalLink size={11} aria-hidden />
                      </a>
                    ))
                  : '—'}
              </dd>
            </div>
            <div>
              <dt>Sosyal hesaplar</dt>
              <dd>{wd.socials.map((s) => s.network).join(', ') || '—'}</dd>
            </div>
          </dl>
        ) : (
          <p className="sg-banner">
            {org.wikidataReason === 'belirsiz'
              ? 'Adı tutan birden çok Wikidata kaydı var; doğru kayda resmî site (timas.com.tr) girilince hangisi olduğu kesinleşir.'
              : 'Wikidata’da Timaş Yayınları kaydı bulunamadı. Kayıt açılmalı: kurum tipi (yayınevi), resmî site, kuruluş yılı, sosyal hesaplar.'}
          </p>
        )}
      </section>
      <section className="sg-card sg-span-12" aria-label="Önerilen şema">
        <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, alignItems: 'start', flexWrap: 'wrap' }}>
          <div>
            <h2>Önerilen kurum şeması (anasayfa)</h2>
            <p className="sg-sub">sameAs listesi Wikidata’dan ve sayfada zaten olanlardan kuruldu. Tema isteğine eklenir; siteye buradan bir şey yazılmaz.</p>
          </div>
          <button className="sg-button" onClick={copy}>
            {copied ? <Check size={16} aria-hidden /> : <Copy size={16} aria-hidden />}
            {copied ? 'Kopyalandı' : 'Kopyala'}
          </button>
        </div>
        <pre className="sg-pre">{org.jsonld}</pre>
      </section>
    </div>
  );
}

function Authors({ filter, setFilter }: { filter: string; setFilter: (v: string) => void }) {
  const [q, setQ] = useState('');
  const [query, setQuery] = useState('');
  const [start, setStart] = useState(0);
  useEffect(() => {
    const t = setTimeout(() => setQuery(q), 300);
    return () => clearTimeout(t);
  }, [q]);
  useEffect(() => setStart(0), [filter, query]);
  const list = useQuery({
    queryKey: ['seo-entity-authors', filter, query, start],
    queryFn: () => api.authors({ status: filter, q: query, start, limit: PAGE }),
    enabled: ENGINE_ENABLED,
    retry: false,
    placeholderData: (p) => p,
  });
  const counts = list.data?.counts;
  const total = list.data?.total ?? 0;
  const all = counts ? Object.values(counts).reduce((a, n) => a + n, 0) : undefined;
  return (
    <>
      <div className="sg-filters" role="toolbar" aria-label="Durum">
        <Chip on={!filter} onClick={() => setFilter('')} label="Tümü" n={all} />
        {STATUS_ORDER.map((s) => (
          <Chip key={s} on={filter === s} onClick={() => setFilter(filter === s ? '' : s)} label={AUTHOR_LABEL[s]} n={counts?.[s]} />
        ))}
      </div>
      <section className="sg-card" aria-label="Yazarlar">
        <label className="sg-search" style={{ marginBottom: 12 }}>
          <Search size={16} aria-hidden />
          <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Yazar adı" aria-label="Yazar ara" />
        </label>
        {list.isLoading && <Loading text="Yazarlar getiriliyor…" />}
        {list.error && <Failed error={list.error} />}
        {list.data && !list.data.items.length && (
          <div className="sg-empty">
            <h2>Yazar yok</h2>
            <p>Bu süzgece uyan yazar bulunamadı.</p>
          </div>
        )}
        {!!list.data?.items.length && (
          <div className="sg-table-wrap">
            <table className="sg-table">
              <thead>
                <tr>
                  <th>Yazar</th>
                  <th style={{ textAlign: 'right' }}>Satış</th>
                  <th>Durum</th>
                  <th>Ne gerekiyor</th>
                </tr>
              </thead>
              <tbody>
                {list.data.items.map((a) => (
                  <tr key={a.name}>
                    <td>
                      <div style={{ fontWeight: 700, color: 'var(--sg-ink)' }}>{a.name}</div>
                      <div style={{ fontSize: 11, color: 'var(--sg-muted)' }}>
                        {fmt(a.books)} kitap{a.description ? ` · ${a.description}` : ''}
                      </div>
                      <div style={{ display: 'flex', gap: 8, marginTop: 4, fontSize: 11.5 }}>
                        {a.wikidata && (
                          <a href={a.wikidata} target="_blank" rel="noreferrer">
                            Wikidata <ExternalLink size={11} aria-hidden />
                          </a>
                        )}
                        {a.wikipedia && (
                          <a href={a.wikipedia} target="_blank" rel="noreferrer">
                            Wikipedia <ExternalLink size={11} aria-hidden />
                          </a>
                        )}
                      </div>
                    </td>
                    <td className="num">{fmt(a.sales)}</td>
                    <td>
                      <span className={`sg-chip ${STATUS_TONE[a.status]}`}>{a.label}</span>
                      <div style={{ fontSize: 11, color: 'var(--sg-muted)', marginTop: 4 }}>{a.checkedAt ? dateTime(a.checkedAt) : ''}</div>
                    </td>
                    <td>
                      {a.needs.length ? (
                        <ul style={{ margin: 0, paddingLeft: 16, fontSize: 12, lineHeight: 1.5 }}>
                          {a.needs.map((n) => (
                            <li key={n}>{n}</li>
                          ))}
                        </ul>
                      ) : (
                        <span style={{ fontSize: 12, color: 'var(--sg-muted)' }}>Sıradaki turda bakılacak.</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <Pager start={start} total={total} setStart={setStart} />
      </section>
    </>
  );
}

const AUTHOR_LABEL: Record<AuthorStatus, string> = {
  wikipedia: 'Wikidata + Wikipedia',
  wikidata: 'Yalnız Wikidata',
  yok: 'Kaydı yok',
  belirsiz: 'Belirsiz',
  bekliyor: 'Henüz bakılmadı',
};
const GB_ORDER: GbCheck[] = ['rights', 'status', 'pdf', 'cover', 'isbn'];
const GB_SHORT: Record<GbCheck, string> = { isbn: 'ISBN', rights: 'Hak', status: 'Yayın durumu', cover: 'Kapak', pdf: 'Tadımlık PDF' };

function GoogleBooks({ filter, setFilter }: { filter: string; setFilter: (v: string) => void }) {
  const [start, setStart] = useState(0);
  useEffect(() => setStart(0), [filter]);
  const ready = filter === 'hazir' ? '1' : filter === 'eksik' ? '0' : undefined;
  const missing = GB_ORDER.includes(filter as GbCheck) ? filter : undefined;
  const list = useQuery({
    queryKey: ['seo-entity-gb', filter, start],
    queryFn: () => api.books({ ready, missing, start, limit: PAGE }),
    enabled: ENGINE_ENABLED,
    retry: false,
    placeholderData: (p) => p,
  });
  const s = list.data?.summary;
  const total = list.data?.total ?? 0;
  return (
    <>
      <p className="sg-banner">
        Google Kitaplar’da önizleme için kitap Play Kitaplar İş Ortağı Merkezi’ne elle yüklenir; burada yalnız hangi kitabın hazır olduğu ve neyin eksik olduğu listelenir. Hak kararı CRM’deki telif alış sözleşmelerinden bir ön süzgeçtir; kesin söz telif biriminindir. Tadımlık PDF yeterli değilse tam metin dosyası ayrıca gerekir.
      </p>
      <div className="sg-filters" role="toolbar" aria-label="Süzgeç">
        <Chip on={!filter} onClick={() => setFilter('')} label="Tümü" n={s?.total} />
        <Chip on={filter === 'hazir'} onClick={() => setFilter(filter === 'hazir' ? '' : 'hazir')} label="Hazır" n={s?.ready} />
        <Chip on={filter === 'eksik'} onClick={() => setFilter(filter === 'eksik' ? '' : 'eksik')} label="Eksiği var" n={s ? s.total - s.ready : undefined} />
        {GB_ORDER.map((k) => (
          <Chip key={k} on={filter === k} onClick={() => setFilter(filter === k ? '' : k)} label={`${GB_SHORT[k]} yok`} n={s?.missing[k]} />
        ))}
      </div>
      <section className="sg-card" aria-label="Kitaplar">
        {list.isLoading && <Loading text="Kitaplar getiriliyor…" />}
        {list.error && <Failed error={list.error} />}
        {list.data && !list.data.items.length && (
          <div className="sg-empty">
            <h2>Kitap yok</h2>
            <p>Bu süzgece uyan kitap bulunamadı.</p>
          </div>
        )}
        {!!list.data?.items.length && (
          <div className="sg-table-wrap">
            <table className="sg-table">
              <thead>
                <tr>
                  <th>Kitap</th>
                  <th style={{ textAlign: 'right' }}>Satış</th>
                  {GB_ORDER.map((k) => (
                    <th key={k}>{GB_SHORT[k]}</th>
                  ))}
                  <th>Durum</th>
                </tr>
              </thead>
              <tbody>
                {list.data.items.map((b) => (
                  <tr key={b.id}>
                    <td>
                      <div style={{ fontWeight: 700, color: 'var(--sg-ink)' }}>
                        {b.url ? (
                          <a href={b.url} target="_blank" rel="noreferrer" style={{ color: 'inherit' }}>
                            {b.name}
                          </a>
                        ) : (
                          b.name
                        )}
                      </div>
                      <div style={{ fontSize: 11, color: 'var(--sg-muted)' }}>
                        {b.author || '—'} · <span className="sg-mono">{b.isbn || 'ISBN yok'}</span>
                        {b.ebookRight ? ' · e-kitap hakkı var' : ''}
                      </div>
                    </td>
                    <td className="num">{fmt(b.sales)}</td>
                    {GB_ORDER.map((k) => (
                      <td key={k} title={k === 'rights' && b.rights ? RIGHTS_LABEL[b.rights] : undefined}>
                        {b.checks[k] ? (
                          <Check size={16} color="#0f7a51" aria-label="Var" />
                        ) : (
                          <X size={16} color="#c2361b" aria-label={k === 'rights' && !b.inCrm ? 'CRM’de yok' : 'Yok'} />
                        )}
                        {k === 'pdf' && b.previewPdf && (
                          <a href={b.previewPdf} target="_blank" rel="noreferrer" aria-label="Tadımlık PDF’i aç" style={{ marginLeft: 4 }}>
                            <ExternalLink size={11} aria-hidden />
                          </a>
                        )}
                      </td>
                    ))}
                    <td>
                      {b.ready ? (
                        <span className="sg-chip good">Hazır</span>
                      ) : (
                        <span className="sg-chip bad" title={b.missing.join(' · ')}>
                          {b.missing.length} eksik
                        </span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <Pager start={start} total={total} setStart={setStart} />
      </section>
    </>
  );
}

function Pager({ start, total, setStart }: { start: number; total: number; setStart: (n: number) => void }) {
  if (total <= PAGE) return null;
  return (
    <div className="sg-pager" style={{ marginTop: 12 }}>
      <button className="sg-button" disabled={start === 0} onClick={() => setStart(Math.max(0, start - PAGE))} aria-label="Önceki sayfa">
        <ChevronLeft size={16} aria-hidden />
      </button>
      <span className="sg-mono">
        {fmt(start + 1)}–{fmt(Math.min(total, start + PAGE))} / {fmt(total)}
      </span>
      <button className="sg-button" disabled={start + PAGE >= total} onClick={() => setStart(start + PAGE)} aria-label="Sonraki sayfa">
        <ChevronRight size={16} aria-hidden />
      </button>
    </div>
  );
}

function Kpi({ label, value, note, tone, info }: { label: string; value: string; note: string; tone?: 'good' | 'bad'; info?: ReactNode }) {
  return (
    <div className="sg-kpi">
      <div className="sg-kpi-label">{label}{info ? <> {info}</> : null}</div>
      <div className="sg-kpi-value sg-mono" style={tone ? { color: tone === 'good' ? '#0f7a51' : '#c2361b' } : undefined}>{value}</div>
      <div className="sg-kpi-note">{note}</div>
    </div>
  );
}

function Chip({ on, onClick, label, n }: { on: boolean; onClick: () => void; label: string; n: number | undefined }) {
  return (
    <button className="sg-filter" aria-pressed={on} onClick={onClick}>
      {label} <span className="sg-mono">{fmt(n ?? 0)}</span>
    </button>
  );
}
