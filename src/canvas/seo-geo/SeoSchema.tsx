import { useState } from 'react';
import { Link } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Download, ExternalLink, Loader2, RefreshCw } from 'lucide-react';
import { ENGINE_ENABLED } from '../engine';
import { dateTime, fmt, seoApi } from './api';
import SeoLayout, { Failed, Loading, SeoInfo } from './SeoLayout';
import { useCan } from '../useAdmin';
import { EmptyHint, Explain } from '../components/Explain';
import { Term } from './terms';
import SeoPager from './SeoPager';

const PAGE = 40;

/** Şema denetimi: canlı kitap sayfalarının yapılandırılmış verisi (JSON-LD), yalnız okunarak taranır. Şemayı T-soft
 *  teması üretir; buradan tema isteği belgesi indirilir. T-soft'a hiçbir şey yazılmaz. */
export default function SeoSchema() {
  // Okuma/tarama/ölçüm başlatmak «SEO eşitleme ve ölçüm» ister; rolde yoksa düğme çıkmaz.
  const canRun = useCan('seo.calistir');
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
    <SeoLayout k={r.data?.kaynaklar}
      path="/seo-geo/sema"
      crumb="Şema denetimi"
      eyebrow="SEO & GEO · yapılandırılmış veri"
      title="Kitap sayfalarının şeması"
      lead={<>Google ve yapay zekâ servisleri kitabın adını, yazarını, fiyatını ve stokunu sayfadaki gizli yapısal veriden okur. <Term k="schema" /> Kitap sayfaları yalnız okunarak taranır, eksikler kitap başına listelenir. Bu veriyi site teması ürettiği için düzeltme, indirilen tema isteği belgesiyle T-soft tarafına iletilir.</>}
      actions={
        <>
          {canRun && <button className="sg-button" onClick={() => crawl.mutate()} disabled={crawl.isPending || d?.crawl.running}>
            {d?.crawl.running ? <Loader2 size={16} className="animate-spin" aria-hidden /> : <RefreshCw size={16} aria-hidden />}
            {d?.crawl.running ? `Taranıyor ${fmt(d.crawl.done)}${d.crawl.queue ? ` / ${fmt(d.crawl.queue)}` : ''}` : 'Taramayı başlat (1 saat)'}
          </button>}
          <a className="sg-button primary" href={seoApi.themeRequestUrl()}>
            <Download size={16} aria-hidden /> Tema isteği belgesini indir
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
              <div className="sg-kpi-label">Taranan kitap sayfası <SeoInfo k={r.data?.kaynaklar} label="Taranan kitap sayfası" /> <Explain label="Taranan kitap sayfası">Canlı sitede açılıp yapısal verisi okunan kitap sayfası sayısı. Tarama sayfaları saniyede bir, yalnız okuyarak açar.</Explain></div>
              <div className="sg-kpi-value sg-mono">{fmt(d.checked)}</div>
              <div className="sg-kpi-note">Son tarama {dateTime(d.lastChecked)} · her gece sürer</div>
            </div>
            <div className="sg-kpi">
              <div className="sg-kpi-label">Sorunlu sayfa <SeoInfo k={r.data?.kaynaklar} label="Sorunlu sayfa" /> <Explain label="Sorunlu sayfa">Yapısal verisinde en az bir eksik bulunan kitap sayfası sayısı. Soldan bir eksik seçerseniz yalnız o eksiği taşıyanlar sayılır.</Explain></div>
              <div className="sg-kpi-value sg-mono">{fmt(d.total)}</div>
              <div className="sg-kpi-note">{issue ? `Süzgeç: ${title(issue)}` : 'En az bir eksiği olan'}</div>
            </div>
            <div className="sg-kpi">
              <div className="sg-kpi-label">Kurum şeması adı <SeoInfo k={r.data?.kaynaklar} label="Kurum şeması adı" /> <Explain label="Kurum şeması adı">Sitenin kendini Google’a hangi kurum adıyla tanıttığı. Google bilgi panelinde ve yapay zekâ cevaplarında bu ad kullanılır; «Timaş Yayınları» olmalı.</Explain></div>
              <div className="sg-kpi-value" style={{ fontSize: 18 }}>{d.organization?.name ?? '—'}</div>
              <div className="sg-kpi-note">{d.organization?.name === 'Timaş Yayınları' ? 'Doğru' : 'Olması gereken: Timaş Yayınları'}</div>
            </div>
          </section>

          {!d.checked && (
            <EmptyHint
              title="Henüz tarama yapılmadı"
              why={canRun ? '«Taramayı başlat»a basın ya da gece taramasını bekleyin. Sayfalar saniyede bir, yalnız okunarak açılır.' : 'Gece taraması bittiğinde sonuçlar burada görünür.'}
            />
          )}

          {d.checked > 0 && (
            <div className="sg-grid">
              <section className="sg-card sg-span-5">
                <h2>Eksikler <SeoInfo k={r.data?.kaynaklar} label="Eksikler" /></h2>
                <p className="sg-sub">Her eksiğin kaç sayfada olduğu ve oranı. Bir eksiğe dokunun, sağda yalnız o sayfalar ve eksiğin neden önemli olduğu görünsün.</p>
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
                {issue && d.checks.find((c) => c.id === issue)?.why && (
                  <p className="sg-banner" style={{ margin: '0 0 10px' }}>{d.checks.find((c) => c.id === issue)?.why}</p>
                )}
                <p className="sg-sub">Çok satandan aza. Kitabın adına dokunursanız Ürün denetiminde açılır. Yazar kimliği için veri Yazar ve kategori ekranındaki Wikidata eşleşmelerinden gelir.</p>
                {!d.items.length && <EmptyHint title="Sorunlu sayfa yok" why="Taranan kitap sayfalarının yapısal verisinde bu süzgece uyan eksik bulunmadı." />}
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
                <SeoPager start={start} total={d.total} size={PAGE} onChange={setStart} />
              </section>
            </div>
          )}
        </>
      )}
    </SeoLayout>
  );
}
