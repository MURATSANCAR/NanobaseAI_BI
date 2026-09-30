import type { ReactNode } from 'react';
import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ChevronDown, ExternalLink, Loader2, RefreshCw, Search } from 'lucide-react';
import { ENGINE_ENABLED } from '../engine';
import { call, dateTime, fmt, qs, scoreTone } from './api';
import SeoLayout, { Failed, Loading, SeoInfo } from './SeoLayout';
import { EmptyHint, Explain, ExplainLabel } from '../components/Explain';
import { Term } from './terms';
import { useCan } from '../useAdmin';
import SeoPager from './SeoPager';

const PAGE = 30;
type CheckId = 'page' | 'page_meta' | 'bio' | 'wikidata' | 'sameas' | 'credits' | 'awards';
type CheckState = 'ok' | 'kismi' | 'eksik' | 'bilinmiyor' | 'uymaz';
type Check = { id: CheckId; title: string; weight: number; state: CheckState; earned: number; detail: string; action: string | null };
type Row = {
  name: string;
  sales: number;
  books: number;
  score: number | null;
  page: { link: string; url: string; id: string } | null;
  wikidata: string | null;
  wikipedia: string | null;
  checks: Check[];
  actions: string[];
};
type Resp = {
  summary: {
    authors: number;
    average: number | null;
    missing: Record<CheckId, number>;
    crmRead: boolean;
    crmLastRead: string | null;
    crmAwards: { records: number; linked: number } | null;
    state: { running: boolean; error: string | null };
  };
  checks: Record<CheckId, { weight: number; title: string }>;
  total: number;
  start: number;
  items: Row[];
};
const STATE: Record<CheckState, { label: string; tone: string }> = {
  ok: { label: 'Tamam', tone: 'good' },
  kismi: { label: 'Kısmen', tone: 'mid' },
  eksik: { label: 'Eksik', tone: 'bad' },
  bilinmiyor: { label: 'Bilinmiyor', tone: '' },
  uymaz: { label: 'Gerekmiyor', tone: '' },
};

/** Yazar sayfası güven sinyalleri: çok satan yazarlar için sayfa, tanıtım metni, kimlik kaydı, şema bağlantısı,
 *  çevirmen/çizer künyesi ve ödül — madde madde, ne yapılacağıyla. Yalnız okunur; hiçbir yere yazılmaz. */
export default function SeoAuthors() {
  const canRun = useCan('seo.calistir');
  const qc = useQueryClient();
  const [missing, setMissing] = useState<CheckId | ''>('');
  const [q, setQ] = useState('');
  const [query, setQuery] = useState('');
  const [start, setStart] = useState(0);
  const [open, setOpen] = useState<string | null>(null);
  useEffect(() => {
    const t = setTimeout(() => setQuery(q), 300);
    return () => clearTimeout(t);
  }, [q]);
  useEffect(() => setStart(0), [missing, query]);

  const list = useQuery({
    queryKey: ['seo-authors-trust', missing, query, start],
    queryFn: () => call<Resp>(`authors-trust?${qs({ missing, q: query, start, limit: PAGE })}`),
    enabled: ENGINE_ENABLED,
    retry: false,
    placeholderData: (p) => p,
    refetchInterval: (s) => (s.state.data?.summary.state.running ? 8000 : false),
  });
  const read = useMutation({
    mutationFn: () => call<{ started: boolean }>('authors-trust/refresh', { method: 'POST' }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['seo-authors-trust'] }),
  });
  const d = list.data;
  const s = d?.summary;
  const total = d?.total ?? 0;
  const running = !!s?.state.running;

  return (
    <SeoLayout k={list.data?.kaynaklar}
      path="/seo-geo/yazar-sayfalari"
      crumb="Yazar sayfaları"
      eyebrow="SEO & GEO · Yazar güven sinyalleri"
      title="Yazar sayfaları"
      lead={<>Google ve yapay zekâ servisleri bir kitabı önerirken yazarın kim olduğuna ve başka kaynakların onu tanıyıp tanımadığına bakar. En çok satan yazardan başlayarak her yazarın sayfası, tanıtım metni, açık kayıtları, çevirmen/çizer künyesi ve ödülleri denetlenir; yazara dokunun, eksikler ve ne yapılacağı açılsın. <Term k="trust" /></>}
      actions={
        canRun && (
          <button className="sg-button" onClick={() => read.mutate()} disabled={read.isPending || running}>
            {running ? <Loader2 size={16} className="animate-spin" aria-hidden /> : <RefreshCw size={16} aria-hidden />}
            {running ? 'CRM okunuyor' : 'CRM yazar bilgisini oku'}
          </button>
        )
      }
    >
      {list.isLoading && <Loading text="Yazarlar getiriliyor…" />}
      {list.error && <Failed error={list.error} />}
      {read.error && <Failed error={read.error} />}
      {s?.state.error && <p className="sg-banner err">Son CRM okuması başarısız: {s.state.error}</p>}

      {d && s && (
        <>
          <section className="sg-kpis" aria-label="Özet">
            <Kpi label="Yazar" value={fmt(s.authors)} note="Satıştaki kitaplardan" info={<SeoInfo k={list.data?.kaynaklar} label="Yazar" />}
              explain="Satıştaki kitapları olan yazar sayısı; liste en çok satan yazardan başlar." />
            <Kpi label="Ortalama güven puanı" value={s.average == null ? '—' : fmt(s.average)} note="Bilinen maddelerin ağırlıklı oranı, 100 üzerinden" info={<SeoInfo k={list.data?.kaynaklar} label="Ortalama güven puanı" />}
              explain="Her yazar için denetlenen maddelerden tamam olanların ağırlıklı oranı (100 üzerinden); durumu bilinmeyen maddeler hesaba girmez. Yazarların ortalaması." />
            <Kpi label="Yazar sayfası yok" value={fmt(s.missing.page)} note="Sitede sayfası bulunamayan yazar" tone={s.missing.page ? 'bad' : undefined} info={<SeoInfo k={list.data?.kaynaklar} label="Yazar sayfası yok" />}
              explain="Sitede kendi sayfası bulunamayan yazarlar; Google ve okur yazar hakkında bilgi alacak bir sayfa bulamaz." />
            <Kpi label="Kimlik kaydı eksik" value={fmt(s.missing.wikidata)} note="Wikidata/Wikipedia’da kaydı yok ya da belirsiz" tone={s.missing.wikidata ? 'bad' : undefined} info={<SeoInfo k={list.data?.kaynaklar} label="Kimlik kaydı eksik" />}
              explain="Wikidata ya da Wikipedia’da kaydı bulunmayan ya da hangi kayıt olduğu kesin olmayan yazarlar. Google ve yapay zekâ servisleri kişiyi bu kayıtlardan tanır." />
          </section>
          <p className="sg-banner">
            {s.crmRead
              ? `CRM yazar bilgisi ${dateTime(s.crmLastRead)} okundu (yalnız özgeçmiş uzunluğu ve ödül sayısı).`
              : 'CRM yazar bilgisi henüz okunmadı; tanıtım metni kaynağı ve ödül maddeleri “bilinmiyor” görünür.'}
            {s.crmAwards && ` CRM’de ${fmt(s.crmAwards.records)} ödül kaydı var, ${fmt(s.crmAwards.linked)} tanesi bir kişiye bağlı.`}
          </p>

          <div className="sg-filters" role="radiogroup" aria-label="Eksik madde">
            <button className="sg-filter" role="radio" aria-checked={!missing} aria-pressed={!missing} onClick={() => setMissing('')}>
              Tümü
            </button>
            {(Object.keys(d.checks) as CheckId[]).map((id) => (
              <button key={id} className="sg-filter" role="radio" aria-checked={missing === id} aria-pressed={missing === id} onClick={() => setMissing(id)}>
                {d.checks[id].title} <span className="sg-mono">{fmt(s.missing[id])}</span>
              </button>
            ))}
          </div>
          <label className="sg-search">
            <Search size={16} aria-hidden />
            <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Yazar adı" aria-label="Yazar ara" />
          </label>

          {!d.items.length && (
            <EmptyHint title="Bu süzgece uyan yazar yok" why={query ? 'Aramayı kısaltın ya da temizleyin.' : 'Üstten «Tümü»nü seçin.'} />
          )}
          <div className="sg-list">
            {d.items.map((r) => {
              const isOpen = open === r.name;
              return (
                <article key={r.name} className="sg-card" style={{ padding: 14 }}>
                  <button
                    className="sg-item"
                    style={{ gridTemplateColumns: 'minmax(0, 1fr) auto', border: 0, padding: 0, background: 'transparent' }}
                    aria-expanded={isOpen}
                    onClick={() => setOpen(isOpen ? null : r.name)}
                  >
                    <span style={{ minWidth: 0 }}>
                      <span className="sg-item-name">{r.name}</span>
                      <span className="sg-item-meta sg-mono">
                        {fmt(r.sales)} satış · {fmt(r.books)} kitap · eksik {r.checks.filter((c) => c.state === 'eksik').length} madde
                      </span>
                    </span>
                    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 8 }}>
                      <span className={`sg-chip ${r.score == null ? '' : scoreTone(r.score)}`}>{r.score == null ? '—' : `${fmt(r.score)} puan`}</span>
                      <ChevronDown size={16} aria-hidden style={{ transform: isOpen ? 'rotate(180deg)' : 'none' }} />
                    </span>
                  </button>
                  {isOpen && (
                    <div style={{ marginTop: 12, display: 'flex', flexDirection: 'column', gap: 8 }}>
                      <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                        {r.page && (
                          <a className="sg-button" href={r.page.url} target="_blank" rel="noreferrer">
                            <ExternalLink size={14} aria-hidden /> Yazar sayfası
                          </a>
                        )}
                        {r.page && (
                          <Link className="sg-button" to={`/seo-geo/sayfalar?tur=model&sayfa=${encodeURIComponent(r.page.id)}`}>
                            Sayfa önerisine git
                          </Link>
                        )}
                        {r.wikidata && (
                          <a className="sg-button" href={r.wikidata} target="_blank" rel="noreferrer">
                            <ExternalLink size={14} aria-hidden /> Wikidata
                          </a>
                        )}
                        {r.wikipedia && (
                          <a className="sg-button" href={r.wikipedia} target="_blank" rel="noreferrer">
                            <ExternalLink size={14} aria-hidden /> Wikipedia
                          </a>
                        )}
                      </div>
                      <div className="sg-table-wrap">
                        <table className="sg-table">
                          <thead>
                            <tr>
                              <th><ExplainLabel label="Madde">Parantezdeki sayı, maddenin güven puanındaki ağırlığıdır; büyük olan daha önemlidir.</ExplainLabel></th>
                              <th><ExplainLabel label="Durum">«Bilinmiyor»: bakılacak veri henüz okunmadı ya da taranmadı. «Gerekmiyor»: madde bu yazar için geçerli değil (ör. CRM’de çevirmen ya da çizer yazılı kitabı yoksa künye maddesi). İkisi de puana katılmaz.</ExplainLabel></th>
                              <th>Ayrıntı ve yapılacak</th>
                            </tr>
                          </thead>
                          <tbody>
                            {r.checks.map((c) => (
                              <tr key={c.id}>
                                <td>
                                  {c.title} <span className="sg-mono" style={{ color: 'var(--sg-muted)' }}>({c.weight})</span>
                                </td>
                                <td>
                                  <span className={`sg-chip ${STATE[c.state].tone}`}>{STATE[c.state].label}</span>
                                </td>
                                <td style={{ fontSize: 12.5 }}>
                                  {c.detail}
                                  {c.action && c.state !== 'ok' && <div style={{ marginTop: 4, color: 'var(--sg-ink)' }}>→ {c.action}</div>}
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    </div>
                  )}
                </article>
              );
            })}
          </div>
          <SeoPager start={start} total={total} size={PAGE} onChange={setStart} style={{ marginTop: 0 }} />
        </>
      )}
    </SeoLayout>
  );
}

function Kpi({ label, value, note, tone, info, explain }: { label: string; value: string; note: string; tone?: 'good' | 'bad'; info?: ReactNode; explain?: ReactNode }) {
  return (
    <div className="sg-kpi">
      <div className="sg-kpi-label">{label}{info ? <> {info}</> : null}{explain ? <> <Explain label={label}>{explain}</Explain></> : null}</div>
      <div className="sg-kpi-value sg-mono" style={tone ? { color: tone === 'good' ? '#0f7a51' : '#c2361b' } : undefined}>{value}</div>
      <div className="sg-kpi-note">{note}</div>
    </div>
  );
}
