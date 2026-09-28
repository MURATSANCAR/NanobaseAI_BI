import type { ReactNode } from 'react';
import { useEffect, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Check, ChevronLeft, ChevronRight, Copy, ExternalLink, Loader2, RefreshCw } from 'lucide-react';
import { ENGINE_ENABLED } from '../engine';
import { call, dateTime, fmt, qs } from './api';
import SeoLayout, { Failed, Loading, SeoInfo } from './SeoLayout';
import { useCan } from '../useAdmin';

const PAGE = 30;
type FlagCode = 'yok' | 'gizli' | 'gomulemez' | 'liste_disi' | 'link_yok' | 'kitap_linki_yok' | 'baslik' | 'kisa' | 'coklu' | 'denetlenmedi';
type Filter = 'hepsi' | 'link_yok' | 'kitap_linki_yok' | 'baslik' | 'kapali' | 'coklu';
type Book = { id: string; name: string; url: string | null; image: string | null; sales: number };
type Row = {
  videoId: string;
  url: string;
  thumbnail: string;
  found: boolean;
  title: string | null;
  channel: string | null;
  publishedAt: string | null;
  durationSec: number | null;
  views: number | null;
  likes: number | null;
  comments: number | null;
  privacy: string | null;
  embeddable: boolean | null;
  descriptionLength: number;
  checkedAt: string | null;
  error: string | null;
  books: Book[];
  flags: Array<{ code: FlagCode; label: string }>;
  suggestions: string[];
};
type Resp = {
  configured: boolean;
  setup?: string[];
  summary: {
    videos: number;
    books: number;
    checked: number;
    found: number;
    totalViews: number;
    flags: Record<FlagCode, number>;
    channels: Array<{ channelId: string | null; channel: string | null; videos: number; views: number }>;
    lastChecked: string | null;
    callsPerRefresh: number;
    dailyQuota: number;
  };
  total: number;
  start: number;
  items: Row[];
  state: { running: boolean; startedAt: string | null; finishedAt: string | null; error: string | null };
};
const TONE: Partial<Record<FlagCode, 'bad' | 'mid' | ''>> = {
  yok: 'bad', gizli: 'bad', gomulemez: 'bad', link_yok: 'bad', kitap_linki_yok: 'mid', baslik: 'mid', kisa: 'mid', liste_disi: 'mid', coklu: '', denetlenmedi: '',
};

/** YouTube video denetimi: CRM'deki kitap tanıtım videoları YouTube'da nasıl duruyor — açıklamada kitabın sayfası,
 *  başlıkta kitabın adı, erişilebilirlik. YouTube'dan yalnız okunur; önerilen açıklama satırını kanal sahibi ekler. */
export default function SeoYoutube() {
  const canRun = useCan('seo.calistir');
  const qc = useQueryClient();
  const [filter, setFilter] = useState<Filter>('hepsi');
  const [start, setStart] = useState(0);
  useEffect(() => setStart(0), [filter]);

  const list = useQuery({
    queryKey: ['seo-youtube', filter, start],
    queryFn: () => call<Resp>(`youtube?${qs({ filter, start, limit: PAGE })}`),
    enabled: ENGINE_ENABLED,
    retry: false,
    placeholderData: (p) => p,
    refetchInterval: (s) => (s.state.data?.state.running ? 5000 : false),
  });
  const refresh = useMutation({
    mutationFn: () => call('youtube/refresh', { method: 'POST' }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['seo-youtube'] }),
  });
  const d = list.data;
  const s = d?.summary;
  const running = !!d?.state.running;
  const total = d?.total ?? 0;
  const closed = s ? s.flags.yok + s.flags.gizli + s.flags.gomulemez : 0;

  return (
    <SeoLayout k={list.data?.kaynaklar}
      path="/seo-geo/youtube"
      crumb="YouTube"
      eyebrow="SEO & GEO · Kitap videoları"
      title="YouTube"
      lead="CRM kitap kartındaki YouTube tanıtım videoları. Açıklamasında kitabın timas.com.tr sayfası olan video izleyeni satın alma sayfasına götürür; başlığında kitabın adı geçen video aramada bulunur. YouTube’dan yalnız okunur; hiçbir şey değiştirilmez."
      actions={
        canRun && d?.configured && (
          <button className="sg-button primary" onClick={() => refresh.mutate()} disabled={refresh.isPending || running}>
            {running ? <Loader2 size={16} className="animate-spin" aria-hidden /> : <RefreshCw size={16} aria-hidden />}
            {running ? 'YouTube okunuyor' : 'YouTube’dan yeniden oku'}
          </button>
        )
      }
    >
      {list.isLoading && <Loading text="Videolar getiriliyor…" />}
      {list.error && <Failed error={list.error} />}
      {refresh.error && <Failed error={refresh.error} />}
      {d?.state.error && <p className="sg-banner err">Son okuma başarısız: {d.state.error}</p>}

      {d && !d.configured && (
        <section className="sg-card">
          <h2>YouTube bağlantısı kurulmamış <SeoInfo k={list.data?.kaynaklar} label="YouTube bağlantısı kurulmamış" /></h2>
          <p className="sg-sub">Video bilgisini okumak için ücretsiz bir YouTube Data API v3 anahtarı gerekir. Anahtar yalnız okuma içindir.</p>
          <ol style={{ margin: 0, paddingLeft: 20, fontSize: 13, lineHeight: 1.7 }}>
            {(d.setup ?? []).map((t) => (
              <li key={t}>{t}</li>
            ))}
          </ol>
        </section>
      )}

      {s && !s.videos && (
        <div className="sg-empty">
          <h2>Videolu kitap yok</h2>
          <p>Satıştaki kitapların CRM kartlarında YouTube bağlantısı bulunamadı. CRM okuması yapılmadıysa önce Haklar ve CRM ekranından okuyun.</p>
        </div>
      )}

      {s && s.videos > 0 && (
        <>
          <section className="sg-kpis" aria-label="Özet">
            <Kpi label="Video" value={fmt(s.videos)} note={`${fmt(s.books)} kitapta · ${fmt(s.checked)} denetlendi`} info={<SeoInfo k={list.data?.kaynaklar} label="Video" />} />
            <Kpi label="Toplam izlenme" value={fmt(s.totalViews)} note={s.lastChecked ? `Son okuma ${dateTime(s.lastChecked)}` : 'Henüz okunmadı'} info={<SeoInfo k={list.data?.kaynaklar} label="Toplam izlenme" />} />
            <Kpi label="Kitap sayfası yok" value={fmt(s.flags.kitap_linki_yok)} note={`Hiç timas.com.tr bağlantısı yok: ${fmt(s.flags.link_yok)}`} tone={s.flags.kitap_linki_yok ? 'bad' : undefined} info={<SeoInfo k={list.data?.kaynaklar} label="Kitap sayfası yok" />} />
            <Kpi label="Başlıkta kitap adı yok" value={fmt(s.flags.baslik)} note="Aramada kitap adıyla bulunmaz" tone={s.flags.baslik ? 'bad' : undefined} info={<SeoInfo k={list.data?.kaynaklar} label="Başlıkta kitap adı yok" />} />
            <Kpi label="Erişilemeyen" value={fmt(closed)} note="Silinmiş, gizli ya da gömülemez" tone={closed ? 'bad' : undefined} info={<SeoInfo k={list.data?.kaynaklar} label="Erişilemeyen" />} />
          </section>

          {s.channels.length > 0 && (
            <section className="sg-card">
              <h2>Kanallar <SeoInfo k={list.data?.kaynaklar} label="Kanallar" /></h2>
              <p className="sg-sub">
                Videoların yayınlandığı kanallar. Bir okuma {fmt(s.callsPerRefresh)} birim harcar; günlük ücretsiz kota {fmt(s.dailyQuota)} birim.
              </p>
              <div className="sg-table-wrap">
                <table className="sg-table">
                  <thead>
                    <tr>
                      <th>Kanal</th>
                      <th style={{ textAlign: 'right' }}>Video</th>
                      <th style={{ textAlign: 'right' }}>İzlenme</th>
                    </tr>
                  </thead>
                  <tbody>
                    {s.channels.map((c) => (
                      <tr key={c.channelId ?? c.channel ?? '?'}>
                        <td>
                          {c.channelId ? (
                            <a href={`https://www.youtube.com/channel/${c.channelId}`} target="_blank" rel="noreferrer">
                              {c.channel || c.channelId}
                            </a>
                          ) : (
                            c.channel || '—'
                          )}
                        </td>
                        <td className="sg-mono" style={{ textAlign: 'right' }}>{fmt(c.videos)}</td>
                        <td className="sg-mono" style={{ textAlign: 'right' }}>{fmt(c.views)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          )}

          <div className="sg-filters" role="radiogroup" aria-label="Süzgeç">
            {([
              ['hepsi', 'Tümü', s.videos],
              ['kitap_linki_yok', 'Kitap sayfası yok', s.flags.kitap_linki_yok],
              ['link_yok', 'Site bağlantısı yok', s.flags.link_yok],
              ['baslik', 'Başlıkta ad yok', s.flags.baslik],
              ['kapali', 'Erişilemeyen', closed],
              ['coklu', 'Birden çok kitapta', s.flags.coklu],
            ] as Array<[Filter, string, number]>).map(([id, label, n]) => (
              <button key={id} className="sg-filter" role="radio" aria-checked={filter === id} aria-pressed={filter === id} onClick={() => setFilter(id)}>
                {label} <span className="sg-mono">{fmt(n)}</span>
              </button>
            ))}
          </div>

          {d && !d.items.length && (
            <div className="sg-empty">
              <h2>Video yok</h2>
              <p>Bu süzgece uyan video bulunamadı.</p>
            </div>
          )}
          <div className="sg-list">
            {d?.items.map((r) => (
              <article key={r.videoId} className="sg-card" style={{ padding: 14 }}>
                <div style={{ display: 'grid', gridTemplateColumns: '112px minmax(0, 1fr)', gap: 12, alignItems: 'start' }}>
                  <a href={r.url} target="_blank" rel="noreferrer" aria-label="Videoyu aç">
                    <img src={r.thumbnail} alt="" loading="lazy" style={{ width: 112, aspectRatio: '16 / 9', objectFit: 'cover', borderRadius: 10, background: 'var(--sg-soft)', display: 'block' }} />
                  </a>
                  <div style={{ minWidth: 0, display: 'flex', flexDirection: 'column', gap: 6 }}>
                    <div className="sg-item-name">{r.title || (r.checkedAt ? 'Başlık okunamadı' : 'Henüz okunmadı')}</div>
                    <div className="sg-item-meta" style={{ whiteSpace: 'normal' }}>
                      {[r.channel, r.views != null ? `${fmt(r.views)} izlenme` : null, r.durationSec != null ? duration(r.durationSec) : null,
                        r.publishedAt ? dateTime(r.publishedAt) : null].filter(Boolean).join(' · ') || r.videoId}
                    </div>
                    <div className="sg-item-meta" style={{ whiteSpace: 'normal' }}>
                      Kitap: {r.books.map((b) => b.name).join(', ')}
                    </div>
                    {r.flags.length > 0 ? (
                      <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                        {r.flags.map((f) => (
                          <span key={f.code} className={`sg-chip ${TONE[f.code] ?? ''}`} style={{ whiteSpace: 'normal' }}>
                            {f.label}
                          </span>
                        ))}
                      </div>
                    ) : (
                      <div>
                        <span className="sg-chip good">Sorun yok</span>
                      </div>
                    )}
                    <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                      <a className="sg-button" href={r.url} target="_blank" rel="noreferrer">
                        <ExternalLink size={14} aria-hidden /> Video
                      </a>
                      {r.books.filter((b) => b.url).map((b) => (
                        <a key={b.id} className="sg-button" href={b.url!} target="_blank" rel="noreferrer">
                          <ExternalLink size={14} aria-hidden /> {r.books.length > 1 ? b.name : 'Kitap sayfası'}
                        </a>
                      ))}
                    </div>
                  </div>
                </div>
                {r.suggestions.length > 0 && r.flags.some((f) => f.code === 'kitap_linki_yok' || f.code === 'link_yok') && (
                  <div style={{ marginTop: 12, display: 'flex', flexDirection: 'column', gap: 6 }}>
                    <p style={{ margin: 0, fontSize: 12, color: 'var(--sg-muted)' }}>Açıklamanın ilk satırına eklenmesi önerilen metin:</p>
                    {r.suggestions.map((t) => (
                      <CopyLine key={t} text={t} />
                    ))}
                  </div>
                )}
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

function duration(sec: number) {
  const h = Math.floor(sec / 3600);
  const m = Math.floor((sec % 3600) / 60);
  const s = sec % 60;
  const mm = String(m).padStart(h ? 2 : 1, '0');
  return `${h ? `${h}:` : ''}${mm}:${String(s).padStart(2, '0')}`;
}

function CopyLine({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  useEffect(() => {
    if (!copied) return;
    const t = setTimeout(() => setCopied(false), 1500);
    return () => clearTimeout(t);
  }, [copied]);
  return (
    <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
      <code className="sg-pre" style={{ flex: '1 1 220px', minWidth: 0, overflowWrap: 'anywhere', margin: 0 }}>{text}</code>
      <button className="sg-button" onClick={() => navigator.clipboard?.writeText(text).then(() => setCopied(true), () => undefined)}>
        {copied ? <Check size={14} aria-hidden /> : <Copy size={14} aria-hidden />} {copied ? 'Kopyalandı' : 'Kopyala'}
      </button>
    </div>
  );
}

function Kpi({ label, value, note, tone, info }: { label: string; value: string; note: string; tone?: 'bad'; info?: ReactNode }) {
  return (
    <div className="sg-kpi">
      <div className="sg-kpi-label">{label}{info ? <> {info}</> : null}</div>
      <div className="sg-kpi-value sg-mono" style={tone ? { color: '#c2361b' } : undefined}>{value}</div>
      <div className="sg-kpi-note">{note}</div>
    </div>
  );
}
