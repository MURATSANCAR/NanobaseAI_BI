import { useState } from 'react';
import { Link } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ChevronLeft, ChevronRight, Download, ExternalLink, Loader2, RefreshCw } from 'lucide-react';
import { ENGINE_ENABLED } from '../engine';
import { dateTime, fmt, seoApi } from './api';
import SeoLayout, { Failed, Loading } from './SeoLayout';

const PAGE = 40;

/** Şema denetimi: canlı kitap sayfalarının yapılandırılmış verisi (JSON-LD), yalnız okunarak taranır. Şemayı T-soft
 *  teması üretir; buradan tema isteği belgesi indirilir. T-soft'a hiçbir şey yazılmaz. */
export default function SeoSchema() {
  const qc = useQueryClient();
  const [issue, setIssue] = useState('');
  const [start, setStart] = useState(0);
  const r = useQuery({
    queryKey: ['seo-schema', issue, start],
    queryFn: () => seoApi.schema({ issue, start, limit: PAGE }),
    enabled: ENGINE_ENABLED,
    retry: false,
    placeholderData: (p) => p,
    refetchInterval: (q) => (q.state.data?.crawl.running ? 15000 : false),
  });
  const crawl = useMutation({ mutationFn: () => seoApi.schemaCrawl(3600), onSuccess: () => qc.invalidateQueries({ queryKey: ['seo-schema'] }) });
  const d = r.data;
  const pct = (n: number) => (d?.checked ? `%${Math.round((100 * n) / d.checked)}` : '—');
  const title = (id: string) => d?.checks.find((c) => c.id === id)?.title ?? id;

  return (
    <SeoLayout
      path="/seo-geo/sema"
      crumb="Şema denetimi"
      eyebrow="SEO & GEO · yapılandırılmış veri"
      title="Kitap sayfalarının şeması"
      lead="Google ve yapay zekâ motorları kitabı, yazarı ve fiyatı sayfadaki yapılandırılmış veriden (schema.org) okur. Sayfalar yalnız okunarak, saniyede bir taranır; eksikler kitap başına listelenir. Şemayı T-soft teması ürettiği için düzeltme tema isteğiyle yapılır."
      actions={
        <>
          <button className="sg-button" onClick={() => crawl.mutate()} disabled={crawl.isPending || d?.crawl.running}>
            {d?.crawl.running ? <Loader2 size={16} className="animate-spin" aria-hidden /> : <RefreshCw size={16} aria-hidden />}
            {d?.crawl.running ? `Taranıyor ${fmt(d.crawl.done)}${d.crawl.queue ? ` / ${fmt(d.crawl.queue)}` : ''}` : 'Taramayı başlat (1 saat)'}
          </button>
          <a className="sg-button primary" href={seoApi.themeRequestUrl()}>
            <Download size={16} aria-hidden /> Tema isteği belgesi
          </a>
        </>
      }
    >
      {r.isLoading && <Loading text="Şema sonuçları getiriliyor…" />}
      {r.error && <Failed error={r.error} />}
      {crawl.error && <Failed error={crawl.error} />}
      {d && (
        <>
          <section className="sg-kpis" aria-label="Özet">
            <div className="sg-kpi">
              <div className="sg-kpi-label">Taranan kitap sayfası</div>
              <div className="sg-kpi-value sg-mono">{fmt(d.checked)}</div>
              <div className="sg-kpi-note">Son tarama {dateTime(d.lastChecked)} · her gece sürer</div>
            </div>
            <div className="sg-kpi">
              <div className="sg-kpi-label">Sorunlu sayfa</div>
              <div className="sg-kpi-value sg-mono">{fmt(d.total)}</div>
              <div className="sg-kpi-note">{issue ? `Süzgeç: ${title(issue)}` : 'En az bir eksiği olan'}</div>
            </div>
            <div className="sg-kpi">
              <div className="sg-kpi-label">Kurum şeması adı</div>
              <div className="sg-kpi-value" style={{ fontSize: 18 }}>{d.organization?.name ?? '—'}</div>
              <div className="sg-kpi-note">{d.organization?.name === 'Timaş Yayınları' ? 'Doğru' : 'Olması gereken: Timaş Yayınları'}</div>
            </div>
          </section>

          {!d.checked && (
            <div className="sg-empty">
              <h2>Henüz tarama yok</h2>
              <p>“Taramayı başlat”a basın ya da gece taramasını bekleyin. Sayfalar saniyede bir, yalnız okunarak açılır.</p>
            </div>
          )}

          {d.checked > 0 && (
            <div className="sg-grid">
              <section className="sg-card sg-span-5">
                <h2>Eksikler</h2>
                <p className="sg-sub">Taranan sayfalarda kaç tanesinde var. Tıklayınca sayfalar süzülür.</p>
                <div className="sg-bars">
                  {d.checks
                    .filter((c) => c.count > 0)
                    .sort((a, b) => b.count - a.count)
                    .map((c) => (
                      <button
                        key={c.id}
                        className="sg-bar-row"
                        style={{ background: 'none', border: 0, textAlign: 'left', cursor: 'pointer', padding: 0, font: 'inherit', fontWeight: issue === c.id ? 800 : 500 }}
                        onClick={() => {
                          setIssue(issue === c.id ? '' : c.id);
                          setStart(0);
                        }}
                        title={c.why}
                      >
                        <span style={{ display: 'flex', gap: 8, alignItems: 'center', minWidth: 0 }}>
                          <i className={`sg-dot ${c.severity}`} aria-hidden />
                          {c.title}
                        </span>
                        <span className="sg-mono">
                          {fmt(c.count)} · {pct(c.count)}
                        </span>
                        <span className="sg-bar">
                          <i style={{ width: `${(100 * c.count) / Math.max(1, d.checked)}%` }} />
                        </span>
                      </button>
                    ))}
                </div>
              </section>

              <section className="sg-card sg-span-7">
                <h2>{issue ? title(issue) : 'Sorunlu sayfalar'}</h2>
                <p className="sg-sub">Çok satandan aza. Yazar kimliği için veri Yazar ve kategori ekranındaki Wikidata eşleşmelerinden gelir.</p>
                <div className="sg-table-wrap">
                  <table className="sg-table">
                    <thead>
                      <tr>
                        <th>Kitap</th>
                        <th>Eksikler</th>
                      </tr>
                    </thead>
                    <tbody>
                      {d.items.map((it) => (
                        <tr key={it.id}>
                          <td style={{ minWidth: 180 }}>
                            <Link to={`/seo-geo/urun-denetimi?urun=${encodeURIComponent(it.id)}`}>{it.name}</Link>{' '}
                            <a href={it.url} target="_blank" rel="noreferrer" aria-label="Sayfayı aç">
                              <ExternalLink size={11} aria-hidden />
                            </a>
                          </td>
                          <td style={{ fontSize: 12 }}>{it.issues.map(title).join(' · ')}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                {d.total > PAGE && (
                  <div className="sg-pager" style={{ marginTop: 12 }}>
                    <button className="sg-button" disabled={start === 0} onClick={() => setStart(Math.max(0, start - PAGE))} aria-label="Önceki sayfa">
                      <ChevronLeft size={16} aria-hidden />
                    </button>
                    <span className="sg-mono">
                      {fmt(start + 1)}–{fmt(Math.min(d.total, start + PAGE))} / {fmt(d.total)}
                    </span>
                    <button className="sg-button" disabled={start + PAGE >= d.total} onClick={() => setStart(start + PAGE)} aria-label="Sonraki sayfa">
                      <ChevronRight size={16} aria-hidden />
                    </button>
                  </div>
                )}
              </section>
            </div>
          )}
        </>
      )}
    </SeoLayout>
  );
}
