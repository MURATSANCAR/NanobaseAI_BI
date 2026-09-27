import { useState, type ReactNode } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ChevronLeft, ChevronRight, ExternalLink, Loader2, RefreshCw } from 'lucide-react';
import { ENGINE_ENABLED } from '../engine';
import { FIELD_LABEL, dateTime, fmt } from './api';
import { oppsApi, type Delta, type ImpactItem, type ImpactStatus, type Metrics, type OppItem, type OppKind } from './api-opps';
import SeoLayout, { Failed, Loading } from './SeoLayout';

const PAGE = 50;

const STATUS_LABEL: Record<ImpactStatus, string> = {
  bekliyor: 'Sitede bekleniyor',
  olculuyor: 'Ölçülüyor',
  tamam: 'Ölçüldü',
  veri_yok: 'Arama verisi yok',
  yenilendi: 'Yerine yenisi onaylandı',
};
const STATUS_TONE: Record<ImpactStatus, string> = { bekliyor: '', olculuyor: 'violet', tamam: 'good', veri_yok: 'mid', yenilendi: '' };
const STATUS_ORDER: ImpactStatus[] = ['bekliyor', 'olculuyor', 'tamam', 'veri_yok', 'yenilendi'];

const pct = (v: number | null | undefined, digits = 1) => (v == null ? '—' : `%${fmt(v * 100, digits)}`);
const signed = (v: number | null | undefined, unit = '%', digits = 0) =>
  v == null ? '—' : `${v > 0 ? '+' : v < 0 ? '−' : ''}${unit === '%' ? '%' : ''}${fmt(Math.abs(v), digits)}${unit === '%' ? '' : ` ${unit}`}`;
const day = (iso: string | null | undefined) =>
  iso ? new Date(`${iso}T12:00:00`).toLocaleDateString('tr-TR', { day: '2-digit', month: '2-digit', year: 'numeric' }) : '—';
const pageLabel = (url: string) => {
  try {
    return decodeURIComponent(new URL(url).pathname) || url;
  } catch {
    return url;
  }
};

/** Fırsatlar ve etki: Search Console'daki yakın sıradaki ve az tıklanan sorgular; onaylanan değişikliklerin sitede
 *  yayına girdikten sonraki etkisi. Search Console'dan yalnız okunur, hiçbir yere yazılmaz. */
export default function SeoOpportunities() {
  const [params, setParams] = useSearchParams();
  const tab = params.get('sekme') === 'etki' ? 'etki' : 'firsatlar';
  const setTab = (t: string) => {
    const next = new URLSearchParams(params);
    if (t === 'etki') next.set('sekme', 'etki');
    else next.delete('sekme');
    setParams(next, { replace: true });
  };

  return (
    <SeoLayout
      path="/seo-geo/firsatlar"
      crumb="Fırsatlar ve etki"
      eyebrow="SEO & GEO · Search Console"
      title="Fırsatlar ve etki"
      lead={
        tab === 'firsatlar'
          ? 'Google’da ilk sayfanın altında kalan ve çok gösterilip az tıklanan aramalar. Ek tıklama tahmini sitenin kendi tıklama oranlarından hesaplanır; son 28 günün kesin verisi, her gece yenilenir.'
          : 'Onaylanan metin hiçbir yere bizden gönderilmez; ölçüm, metin sitede göründüğü gün başlar (gece eşitlemesinde ürünün canlı alanları onaylanan metinle aynı görüldüğünde). O günden önceki 28 gün ile sonraki 28 gün karşılaştırılır; Search Console’un kesin verisi 3 gün geç geldiği için sonuç yayından 31 gün sonra çıkar. Site geneli değişim karşılaştırma içindir.'
      }
    >
      <div className="sg-filters" role="toolbar" aria-label="Bölüm">
        <button className="sg-filter" aria-pressed={tab === 'firsatlar'} onClick={() => setTab('firsatlar')}>
          Fırsatlar
        </button>
        <button className="sg-filter" aria-pressed={tab === 'etki'} onClick={() => setTab('etki')}>
          Değişikliğin etkisi
        </button>
      </div>
      {tab === 'firsatlar' ? <Opportunities /> : <ImpactList />}
    </SeoLayout>
  );
}

// ------------------------------------------------------------------ Fırsatlar

function Opportunities() {
  const qc = useQueryClient();
  const [kind, setKind] = useState<OppKind>('yakin');
  const [brand, setBrand] = useState('0');
  const [start, setStart] = useState(0);
  const r = useQuery({
    queryKey: ['seo-opps', kind, brand, start],
    queryFn: () => oppsApi.opportunities({ kind, brand, start, limit: PAGE }),
    enabled: ENGINE_ENABLED,
    retry: false,
    placeholderData: (p) => p,
  });
  const refresh = useMutation({ mutationFn: oppsApi.refreshOpportunities, onSuccess: () => qc.invalidateQueries({ queryKey: ['seo-opps'] }) });
  const d = r.data;
  const t = d?.thresholds;
  const pick = (k: OppKind) => {
    setKind(k);
    setStart(0);
  };
  const pickBrand = (b: string) => {
    setBrand(b);
    setStart(0);
  };
  const count = (k: OppKind) => (d ? (brand === '1' ? d.totals[k].brand : brand === '0' ? d.totals[k].nonBrand : d.totals[k].all) : undefined);

  return (
    <>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, justifyContent: 'space-between', alignItems: 'center' }}>
        <p className="sg-sub" style={{ margin: 0, fontSize: 12, color: 'var(--sg-muted)' }}>
          {d?.source.savedAt ? `Son okuma ${dateTime(d.source.savedAt)} · ${day(d.source.start)} – ${day(d.source.end)}` : 'Henüz okuma yok'}
        </p>
        <button className="sg-button" onClick={() => refresh.mutate()} disabled={refresh.isPending || (d && !d.connected)}>
          {refresh.isPending ? <Loader2 size={16} className="animate-spin" aria-hidden /> : <RefreshCw size={16} aria-hidden />}
          {refresh.isPending ? 'Search Console okunuyor…' : 'Search Console’dan yeniden oku'}
        </button>
      </div>

      {r.isLoading && <Loading text="Fırsatlar hesaplanıyor…" />}
      {r.error && <Failed error={r.error} />}
      {refresh.error && <Failed error={refresh.error} />}
      {refresh.data && <p className="sg-banner ok">{fmt(refresh.data.rows)} arama–sayfa satırı okundu.</p>}
      {d && !d.connected && <p className="sg-banner">Search Console bağlı değil. Bağlantı Yönetim → SEO & GEO ekranından kurulur.</p>}
      {d?.source.from === 'queries' && (
        <p className="sg-banner">Şimdilik yalnız arama sözcükleri var; hangi sayfanın göründüğü bir sonraki okumada gelir.</p>
      )}

      {d && (
        <>
          <section className="sg-kpis" aria-label="Özet">
            <Kpi
              label="Yakın sıradaki arama"
              value={fmt(d.totals.yakin.nonBrand)}
              note={`${fmt(t!.nearMin)}–${fmt(t!.nearMax)}. sıra · marka araması ayrıca ${fmt(d.totals.yakin.brand)}`}
            />
            <Kpi label="İlk üçe çıkınca ek tıklama" value={fmt(d.totals.yakin.clicks)} note="28 günde, marka dışı aramalarda tahmini" />
            <Kpi
              label="Az tıklanan arama"
              value={fmt(d.totals.dusuk_tiklama.nonBrand)}
              note={`Aynı sıranın tipik oranının yarısından az · en az ${fmt(t!.lowMinImpressions)} gösterim`}
            />
            <Kpi label="Kaçan tıklama" value={fmt(d.totals.dusuk_tiklama.clicks)} note="Tipik orana ulaşsa gelecek, marka dışı" />
          </section>

          <div className="sg-filters" role="toolbar" aria-label="Fırsat türü">
            <Chip on={kind === 'yakin'} onClick={() => pick('yakin')} label="Yakın sıra" n={count('yakin')} />
            <Chip on={kind === 'dusuk_tiklama'} onClick={() => pick('dusuk_tiklama')} label="Düşük tıklama" n={count('dusuk_tiklama')} />
            <span style={{ width: 8 }} aria-hidden />
            <Chip on={brand === '0'} onClick={() => pickBrand('0')} label="Marka dışı" />
            <Chip on={brand === '1'} onClick={() => pickBrand('1')} label="Marka araması" />
            <Chip on={brand === ''} onClick={() => pickBrand('')} label="Hepsi" />
          </div>

          {!d.source.rowCount ? (
            <div className="sg-empty">
              <h2>Arama verisi yok</h2>
              <p>
                {d.connected
                  ? '“Search Console’dan yeniden oku”ya basın ya da gece okumasını bekleyin.'
                  : 'Search Console bağlanınca son 28 günün aramaları burada fırsata dönüşür.'}
              </p>
            </div>
          ) : (
            <section className="sg-card">
              <h2>{kind === 'yakin' ? 'Yakın sıradaki aramalar' : 'Çok gösterilip az tıklananlar'}</h2>
              <p className="sg-sub">
                {kind === 'yakin'
                  ? `Ortalama sırası ${fmt(t!.nearMin)} ile ${fmt(t!.nearMax)} arasında; gösterime göre sıralı. Ek tıklama, sitenizde ${fmt(t!.targetPosition)}. sıradaki aramaların tipik oranıyla hesaplanır. İçerik, iç bağlantı ve başlık güçlendirmesi burada en hızlı karşılığı verir.`
                  : 'Sıra fena değil ama başlık ve açıklama tıklatmıyor. Kitap sayfası eşleştiyse ürün denetiminde yeni başlık ve açıklama önerisi isteyin. Kaçan tıklamaya göre sıralı.'}
              </p>
              {!d.items.length ? (
                <div className="sg-empty">
                  <h2>Bu süzgeçte fırsat yok</h2>
                  <p>Marka araması süzgecini değiştirmeyi deneyin.</p>
                </div>
              ) : (
                <OppTable items={d.items} kind={kind} />
              )}
              <Pager start={start} total={d.total} onChange={setStart} />
              {d.curve.length > 0 && (
                <details className="sg-more" style={{ marginTop: 12 }}>
                  <summary>Sitenin kendi tıklama oranı eğrisi</summary>
                  <p>
                    Marka dışı, en az {fmt(t!.curveMinImpressions)} gösterimli aramaların sıraya göre ortanca tıklama oranı. Bir sırada {fmt(t!.curveMinSamples)}{' '}
                    aramadan az varsa değer komşu sıralardan doldurulur.
                  </p>
                  <div className="sg-table-wrap" style={{ marginTop: 8 }}>
                    <table className="sg-table">
                      <thead>
                        <tr>
                          <th>Sıra</th>
                          <th>Tipik oran</th>
                          <th>Arama sayısı</th>
                        </tr>
                      </thead>
                      <tbody>
                        {d.curve.map((c) => (
                          <tr key={c.position}>
                            <td className="num">{c.position === d.curve.length ? `${c.position}+` : c.position}</td>
                            <td className="num">{pct(c.ctr)}</td>
                            <td className="num">{c.measured ? fmt(c.samples) : `${fmt(c.samples)} (dolduruldu)`}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </details>
              )}
            </section>
          )}
        </>
      )}
    </>
  );
}

function OppTable({ items, kind }: { items: OppItem[]; kind: OppKind }) {
  return (
    <div className="sg-table-wrap">
      <table className="sg-table">
        <thead>
          <tr>
            <th>Arama</th>
            <th>Sayfa</th>
            <th>Gösterim</th>
            <th>Tıklama</th>
            <th>Oran</th>
            <th>Sıra</th>
            <th>{kind === 'yakin' ? 'İlk üçte ek tıklama' : 'Kaçan tıklama'}</th>
          </tr>
        </thead>
        <tbody>
          {items.map((i) => (
            <tr key={`${i.query}|${i.page ?? ''}`}>
              <td style={{ minWidth: 160 }}>
                {i.query} {i.brand && <span className="sg-chip violet">Marka</span>}
              </td>
              <td style={{ minWidth: 180 }}>
                {i.productId ? (
                  <Link to={`/seo-geo/urun-denetimi?urun=${encodeURIComponent(i.productId)}`}>{i.productName || pageLabel(i.page!)}</Link>
                ) : i.page ? (
                  <span className="sg-mono" style={{ fontSize: 11.5, wordBreak: 'break-all' }}>
                    {pageLabel(i.page)}
                  </span>
                ) : (
                  '—'
                )}{' '}
                {i.page && (
                  <a href={i.page} target="_blank" rel="noreferrer" aria-label="Sayfayı aç">
                    <ExternalLink size={11} aria-hidden />
                  </a>
                )}
              </td>
              <td className="num">{fmt(i.impressions)}</td>
              <td className="num">{fmt(i.clicks)}</td>
              <td className="num" title={i.expectedCtr != null ? `Bu sırada tipik: ${pct(i.expectedCtr)}` : undefined}>
                {pct(i.ctr)}
                {kind === 'dusuk_tiklama' && i.expectedCtr != null && <div style={{ fontSize: 11, color: 'var(--sg-muted)' }}>tipik {pct(i.expectedCtr)}</div>}
              </td>
              <td className="num">{fmt(i.position, 1)}</td>
              <td className="num">{kind === 'yakin' ? (i.extraClicks == null ? '—' : `+${fmt(i.extraClicks)}`) : fmt(i.lostClicks)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ------------------------------------------------------------------ Değişikliğin etkisi

function ImpactList() {
  const qc = useQueryClient();
  const [status, setStatus] = useState<ImpactStatus | ''>('');
  const [start, setStart] = useState(0);
  const r = useQuery({
    queryKey: ['seo-impact', status, start],
    queryFn: () => oppsApi.impact({ status, start, limit: PAGE }),
    enabled: ENGINE_ENABLED,
    retry: false,
    placeholderData: (p) => p,
    refetchInterval: (q) => (q.state.data?.summary.state.running ? 5000 : false),
  });
  const run = useMutation({ mutationFn: oppsApi.runImpact, onSuccess: () => qc.invalidateQueries({ queryKey: ['seo-impact'] }) });
  const d = r.data;
  const s = d?.summary;
  const running = !!s?.state.running;
  const all = s ? STATUS_ORDER.reduce((a, k) => a + s.counts[k], 0) : undefined;

  return (
    <>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, justifyContent: 'space-between', alignItems: 'center' }}>
        <p style={{ margin: 0, fontSize: 12, color: 'var(--sg-muted)' }}>
          {s?.state.finishedAt ? `Son denetim ${dateTime(s.state.finishedAt)} · her gece sürer` : 'Her gece, ürün eşitlemesinden sonra denetlenir'}
        </p>
        <button className="sg-button" onClick={() => run.mutate()} disabled={run.isPending || running}>
          {running ? <Loader2 size={16} className="animate-spin" aria-hidden /> : <RefreshCw size={16} aria-hidden />}
          {running ? 'Denetleniyor…' : 'Şimdi denetle'}
        </button>
      </div>

      {r.isLoading && <Loading text="Onaylanan değişiklikler getiriliyor…" />}
      {r.error && <Failed error={r.error} />}
      {run.error && <Failed error={run.error} />}
      {s?.state.error && <p className="sg-banner err">Son denetim başarısız: {s.state.error}</p>}
      {s && !s.connected && (
        <p className="sg-banner">Search Console bağlı değil: metnin sitede göründüğü gün yine kaydedilir, önce/sonra ölçümü bağlantı kurulunca yapılır.</p>
      )}

      {s && (
        <>
          <section className="sg-kpis" aria-label="Özet">
            <Kpi label="Sitede bekleniyor" value={fmt(s.counts.bekliyor)} note="Onaylı; metin sitede henüz görünmüyor" />
            <Kpi label="Ölçülüyor" value={fmt(s.counts.olculuyor)} note={`Yayında; ${s.windowDays}+${s.lagDays} gün dolunca ölçülür`} />
            <Kpi label="Ölçüldü" value={fmt(s.counts.tamam)} note="Önce/sonra karşılaştırması hazır" />
            <Kpi label="Arama verisi yok" value={fmt(s.counts.veri_yok)} note="İki dönemde de Google’da gösterim yok" />
          </section>

          <div className="sg-filters" role="toolbar" aria-label="Durum">
            <Chip on={!status} onClick={() => {
                setStatus('');
                setStart(0);
              }} label="Tümü" n={all} />
            {STATUS_ORDER.map((k) => (
              <Chip key={k} on={status === k} onClick={() => {
                  setStatus(status === k ? '' : k);
                  setStart(0);
                }} label={STATUS_LABEL[k]} n={s.counts[k]} />
            ))}
          </div>

          {!d!.items.length ? (
            <div className="sg-empty">
              <h2>{all ? 'Bu durumda değişiklik yok' : 'Henüz onaylanan değişiklik yok'}</h2>
              <p>
                {all
                  ? 'Başka bir durum seçin.'
                  : 'Ürün denetiminde bir öneri onaylandığında burada görünür; metin sitede yayına girince ölçüm başlar.'}
              </p>
            </div>
          ) : (
            <section className="sg-card">
              <h2>Onaylanan değişiklikler</h2>
              <p className="sg-sub">
                Oklar önceki 28 günden sonraki 28 güne değişimi gösterir. “Siteye göre” sütunu, kitabın tıklama değişiminden site genelindeki değişimin
                çıkarılmış hâlidir: mevsim ve genel trafik etkisini ayırmak için.
              </p>
              <div className="sg-table-wrap">
                <table className="sg-table">
                  <thead>
                    <tr>
                      <th>Kitap</th>
                      <th>Değişen alan</th>
                      <th>Onay / yayın</th>
                      <th>Tıklama</th>
                      <th>Gösterim</th>
                      <th>Oran</th>
                      <th>Sıra</th>
                      <th>Site geneli</th>
                      <th>Siteye göre</th>
                      <th>Durum</th>
                    </tr>
                  </thead>
                  <tbody>
                    {d!.items.map((i) => (
                      <ImpactRow key={i.proposalId} i={i} />
                    ))}
                  </tbody>
                </table>
              </div>
              <Pager start={start} total={d!.total} onChange={setStart} />
            </section>
          )}
        </>
      )}
    </>
  );
}

function ImpactRow({ i }: { i: ImpactItem }) {
  const has = i.status === 'tamam' || i.status === 'veri_yok';
  const note =
    i.status === 'bekliyor'
      ? 'Metin sitede görününce ölçüm başlar'
      : i.status === 'olculuyor' && i.windows
        ? `Sonuç ${day(i.windows.dueOn)} tarihinde`
        : null;
  return (
    <tr>
      <td style={{ minWidth: 180 }}>
        <Link to={`/seo-geo/urun-denetimi?urun=${encodeURIComponent(i.productId)}`}>{i.productName || i.productId}</Link>{' '}
        {i.url && (
          <a href={i.url} target="_blank" rel="noreferrer" aria-label="Sayfayı aç">
            <ExternalLink size={11} aria-hidden />
          </a>
        )}
      </td>
      <td style={{ fontSize: 12, minWidth: 120 }}>{i.fields.map((f) => FIELD_LABEL[f] ?? f).join(', ') || '—'}</td>
      <td style={{ fontSize: 12, whiteSpace: 'nowrap' }}>
        <div>Onay {i.decidedAt ? new Date(i.decidedAt).toLocaleDateString('tr-TR') : '—'}</div>
        <div style={{ color: 'var(--sg-muted)' }}>Yayın {day(i.appliedAt)}</div>
      </td>
      {has ? (
        <>
          <Cell b={fmt(i.before?.clicks)} a={fmt(i.after?.clicks)} d={signed(i.delta?.clicksPct)} good={sign(i.delta?.clicksPct)} />
          <Cell b={fmt(i.before?.impressions)} a={fmt(i.after?.impressions)} d={signed(i.delta?.impressionsPct)} good={sign(i.delta?.impressionsPct)} />
          <Cell b={pct(i.before?.ctr)} a={pct(i.after?.ctr)} d={signed(i.delta?.ctrPt, 'puan', 1)} good={sign(i.delta?.ctrPt)} />
          <Cell b={fmt(i.before?.position, 1)} a={fmt(i.after?.position, 1)} d={signed(i.delta?.position, 'sıra', 1)} good={sign(neg(i.delta?.position))} />
          <td className="num" style={{ fontSize: 12 }}>
            <Control d={i.control?.delta ?? null} m={i.control?.after ?? null} />
          </td>
          <td className="num">
            <Tone good={sign(i.netClicksPct)}>{signed(i.netClicksPct, 'puan', 0)}</Tone>
          </td>
        </>
      ) : (
        <td colSpan={6} style={{ fontSize: 12, color: 'var(--sg-muted)' }}>
          {note}
          {i.error && <div style={{ color: '#9b1c24' }}>Son ölçüm denemesi: {i.error}</div>}
        </td>
      )}
      <td>
        <span className={`sg-chip ${STATUS_TONE[i.status]}`}>{STATUS_LABEL[i.status]}</span>
      </td>
    </tr>
  );
}

const sign = (v: number | null | undefined): boolean | null => (v == null || v === 0 ? null : v > 0);
/** Sırada küçük sayı iyidir: işareti çevrilerek renklenir. */
const neg = (v: number | null | undefined) => (v == null ? null : -v);

function Tone({ good, children }: { good: boolean | null; children: ReactNode }) {
  return <span style={good == null ? undefined : { color: good ? '#0f7a51' : '#c2361b', fontWeight: 700 }}>{children}</span>;
}

function Cell({ b, a, d, good }: { b: string; a: string; d: string; good: boolean | null }) {
  return (
    <td className="num">
      <div>
        {b} → {a}
      </div>
      <div style={{ fontSize: 11 }}>
        <Tone good={good}>{d}</Tone>
      </div>
    </td>
  );
}

function Control({ d, m }: { d: Delta | null; m: Metrics | null }) {
  if (!d || !m) return <>—</>;
  return (
    <>
      <div>Tıklama {signed(d.clicksPct)}</div>
      <div style={{ fontSize: 11, color: 'var(--sg-muted)' }}>Gösterim {signed(d.impressionsPct)}</div>
    </>
  );
}

// ------------------------------------------------------------------ ortak

function Pager({ start, total, onChange }: { start: number; total: number; onChange: (n: number) => void }) {
  if (total <= PAGE) return null;
  return (
    <div className="sg-pager" style={{ marginTop: 12 }}>
      <button className="sg-button" disabled={start === 0} onClick={() => onChange(Math.max(0, start - PAGE))} aria-label="Önceki sayfa">
        <ChevronLeft size={16} aria-hidden />
      </button>
      <span className="sg-mono">
        {fmt(start + 1)}–{fmt(Math.min(total, start + PAGE))} / {fmt(total)}
      </span>
      <button className="sg-button" disabled={start + PAGE >= total} onClick={() => onChange(start + PAGE)} aria-label="Sonraki sayfa">
        <ChevronRight size={16} aria-hidden />
      </button>
    </div>
  );
}

function Kpi({ label, value, note }: { label: string; value: string; note: string }) {
  return (
    <div className="sg-kpi">
      <div className="sg-kpi-label">{label}</div>
      <div className="sg-kpi-value sg-mono">{value}</div>
      <div className="sg-kpi-note">{note}</div>
    </div>
  );
}

function Chip({ on, onClick, label, n }: { on: boolean; onClick: () => void; label: string; n?: number }) {
  return (
    <button className="sg-filter" aria-pressed={on} onClick={onClick}>
      {label} {n !== undefined && <span className="sg-mono">{fmt(n)}</span>}
    </button>
  );
}
