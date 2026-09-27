import { useEffect, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Check, ChevronLeft, ChevronRight, Copy, Download, ExternalLink, FileText } from 'lucide-react';
import { ENGINE_BASE, ENGINE_ENABLED } from '../engine';
import { call, fmt, qs } from './api';
import SeoLayout, { Failed, Loading } from './SeoLayout';
import { useCan } from '../useAdmin';

const PAGE = 30;
type SchemaState = 'var' | 'yok' | 'bilinmiyor';
type Row = {
  id: string;
  name: string;
  image: string | null;
  url: string | null;
  sales: number;
  video: string;
  youtubeId: string | null;
  thumbnail: string | null;
  schema: SchemaState;
  schemaLabel: string;
  jsonld: string | null;
};
type Resp = {
  summary: { withVideo: number; valid: number; invalid: number; schema: Record<SchemaState, number> };
  labels: Record<SchemaState, string>;
  total: number;
  start: number;
  items: Row[];
};
type Filter = '' | SchemaState | 'gecersiz';
const TONE: Record<SchemaState, string> = { var: 'good', yok: 'bad', bilinmiyor: '' };

/** Kitap videoları: CRM'deki YouTube tanıtım videoları için sayfaya konacak video şeması önerisi, video site haritası
 *  ve tema isteği. Siteye hiçbir şey yazılmaz; dosyalar site yöneticisine verilir. */
export default function SeoVideo() {
  const canExport = useCan('veri.disa-aktar');
  const [filter, setFilter] = useState<Filter>('');
  const [start, setStart] = useState(0);
  const [open, setOpen] = useState<string | null>(null);
  useEffect(() => setStart(0), [filter]);

  const list = useQuery({
    queryKey: ['seo-video', filter, start],
    queryFn: () => call<Resp>(`video?${qs({ filter, start, limit: PAGE })}`),
    enabled: ENGINE_ENABLED,
    retry: false,
    placeholderData: (p) => p,
  });
  const s = list.data?.summary;
  const total = list.data?.total ?? 0;

  return (
    <SeoLayout
      path="/seo-geo/video"
      crumb="Video"
      eyebrow="SEO & GEO · Kitap videoları"
      title="Kitap videoları"
      lead="CRM kitap kartında YouTube tanıtım videosu olan kitaplar. Video sayfada gömülü ve video şemasıyla işaretliyse Google video sonuçlarında ve yapay zekâ cevaplarında kitabı videosuyla gösterebilir. Buradaki şema ve site haritası öneridir; siteye hiçbir şey yazılmaz."
      actions={
        canExport && (
          <>
            <a className="sg-button" href={`${ENGINE_BASE}/api/v1/seo-geo/video/sitemap.xml`}>
              <Download size={16} aria-hidden /> Video site haritası
            </a>
            <a className="sg-button primary" href={`${ENGINE_BASE}/api/v1/seo-geo/video/theme-request.md`}>
              <FileText size={16} aria-hidden /> Tema isteği
            </a>
          </>
        )
      }
    >
      {list.isLoading && <Loading text="Videolar getiriliyor…" />}
      {list.error && <Failed error={list.error} />}

      {s && !s.withVideo && (
        <div className="sg-empty">
          <h2>Videolu kitap yok</h2>
          <p>Satıştaki kitapların CRM kartlarında YouTube bağlantısı bulunamadı. CRM okuması yapılmadıysa önce Haklar ve CRM ekranından okuyun.</p>
        </div>
      )}

      {s && s.withVideo > 0 && (
        <>
          <section className="sg-kpis" aria-label="Özet">
            <Kpi label="Videolu kitap" value={fmt(s.withVideo)} note={`Geçerli video bağlantısı ${fmt(s.valid)}`} />
            <Kpi label="Sayfada video şeması var" value={fmt(s.schema.var)} note="Şema taramasına göre" tone="good" />
            <Kpi label="Video şeması yok" value={fmt(s.schema.yok)} note="Videonun sayfada gömülü olup olmadığı bilinmiyor" tone={s.schema.yok ? 'bad' : undefined} />
            <Kpi label="Bağlantı geçersiz" value={fmt(s.invalid)} note="Kanal ya da liste bağlantısı; CRM’de video adresi düzeltilmeli" tone={s.invalid ? 'bad' : undefined} />
          </section>

          <div className="sg-filters" role="radiogroup" aria-label="Süzgeç">
            {([
              ['', 'Tümü', s.withVideo],
              ['yok', 'Şeması yok', s.schema.yok],
              ['bilinmiyor', 'Taranmadı', s.schema.bilinmiyor],
              ['var', 'Şeması var', s.schema.var],
              ['gecersiz', 'Geçersiz bağlantı', s.invalid],
            ] as Array<[Filter, string, number]>).map(([id, label, n]) => (
              <button key={id || 'hepsi'} className="sg-filter" role="radio" aria-checked={filter === id} aria-pressed={filter === id} onClick={() => setFilter(id)}>
                {label} <span className="sg-mono">{fmt(n)}</span>
              </button>
            ))}
          </div>

          {list.data && !list.data.items.length && (
            <div className="sg-empty">
              <h2>Kitap yok</h2>
              <p>Bu süzgece uyan kitap bulunamadı.</p>
            </div>
          )}
          <div className="sg-list">
            {list.data?.items.map((r) => (
              <article key={r.id} className="sg-card" style={{ padding: 14 }}>
                <div style={{ display: 'grid', gridTemplateColumns: '96px minmax(0, 1fr)', gap: 12, alignItems: 'start' }}>
                  {r.thumbnail ? (
                    <img src={r.thumbnail} alt="" loading="lazy" style={{ width: 96, aspectRatio: '4 / 3', objectFit: 'cover', borderRadius: 10, background: 'var(--sg-soft)' }} />
                  ) : (
                    <span style={{ width: 96, aspectRatio: '4 / 3', borderRadius: 10, background: 'var(--sg-soft)' }} aria-hidden />
                  )}
                  <div style={{ minWidth: 0, display: 'flex', flexDirection: 'column', gap: 6 }}>
                    <div className="sg-item-name">{r.name}</div>
                    <div className="sg-item-meta sg-mono">{fmt(r.sales)} satış</div>
                    <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                      {r.youtubeId ? <span className={`sg-chip ${TONE[r.schema]}`}>{r.schemaLabel}</span> : <span className="sg-chip bad">Video bağlantısı geçersiz</span>}
                    </div>
                    <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                      <a className="sg-button" href={r.video} target="_blank" rel="noreferrer">
                        <ExternalLink size={14} aria-hidden /> Video
                      </a>
                      {r.url && (
                        <a className="sg-button" href={r.url} target="_blank" rel="noreferrer">
                          <ExternalLink size={14} aria-hidden /> Kitap sayfası
                        </a>
                      )}
                      {r.jsonld && (
                        <button className="sg-button" aria-expanded={open === r.id} onClick={() => setOpen(open === r.id ? null : r.id)}>
                          {open === r.id ? 'Şemayı gizle' : 'Önerilen şema'}
                        </button>
                      )}
                    </div>
                  </div>
                </div>
                {open === r.id && r.jsonld && <JsonBlock text={r.jsonld} />}
              </article>
            ))}
          </div>
          {total > PAGE && (
            <div className="sg-pager">
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
          )}
        </>
      )}
    </SeoLayout>
  );
}

function JsonBlock({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  useEffect(() => {
    if (!copied) return;
    const t = setTimeout(() => setCopied(false), 1500);
    return () => clearTimeout(t);
  }, [copied]);
  return (
    <div style={{ marginTop: 12 }}>
      <p style={{ margin: '0 0 6px', fontSize: 12, color: 'var(--sg-muted)' }}>
        Yayın tarihi (uploadDate) Google için zorunludur; CRM’de olmadığı için tema YouTube’dan ya da elle doldurmalı.
      </p>
      <pre className="sg-pre" style={{ overflowX: 'auto', maxWidth: '100%' }}>{text}</pre>
      <button
        className="sg-button"
        style={{ marginTop: 6 }}
        onClick={() => navigator.clipboard?.writeText(text).then(() => setCopied(true), () => undefined)}
      >
        {copied ? <Check size={14} aria-hidden /> : <Copy size={14} aria-hidden />} {copied ? 'Kopyalandı' : 'Kopyala'}
      </button>
    </div>
  );
}

function Kpi({ label, value, note, tone }: { label: string; value: string; note: string; tone?: 'good' | 'bad' }) {
  return (
    <div className="sg-kpi">
      <div className="sg-kpi-label">{label}</div>
      <div className="sg-kpi-value sg-mono" style={tone ? { color: tone === 'good' ? '#0f7a51' : '#c2361b' } : undefined}>{value}</div>
      <div className="sg-kpi-note">{note}</div>
    </div>
  );
}
