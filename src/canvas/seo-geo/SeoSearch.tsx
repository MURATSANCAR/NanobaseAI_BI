import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Loader2, RefreshCw, Search } from 'lucide-react';
import { ENGINE_ENABLED } from '../engine';
import { dateTime, fmt, seoApi, type SearchCompare, type SearchReport, type SearchRow } from './api';
import SeoLayout, { Failed, Loading } from './SeoLayout';
import SeoPager from './SeoPager';
import { useCan } from '../useAdmin';
import { EmptyHint } from '../components/Explain';
import { TermLabel } from './terms';

type Kind = 'queries' | 'pages';
type Bounds = NonNullable<SearchReport['bounds']>;
/** Hazır aralıklar (ZEKI-50). `kayit`: her gece kaydedilen son 28 kesin gün — açılışta bu gelir, Google'a gidilmez. */
type Preset = 'kayit' | 'son7' | 'son28' | 'son90' | 'gecenAy' | 'ozel';

const PAGE = 100;
const PRESETS: Array<{ id: Preset; label: string }> = [
  { id: 'kayit', label: 'Kayıtlı (her gece)' },
  { id: 'son7', label: 'Son 7 gün' },
  { id: 'son28', label: 'Son 28 gün' },
  { id: 'son90', label: 'Son 3 ay' },
  { id: 'gecenAy', label: 'Geçen ay' },
  { id: 'ozel', label: 'Özel aralık' },
];
const COMPARE_LABEL: Record<SearchCompare, string> = { onceki: 'önceki dönem', gecen_yil: 'geçen yılın aynı günleri' };

/** YYYY-AA-GG üzerinde gün aritmetiği (UTC: yaz saati kayması yok). */
const addDays = (iso: string, n: number) => {
  const [y, m, d] = iso.split('-').map(Number);
  return new Date(Date.UTC(y, m - 1, d + n)).toISOString().slice(0, 10);
};
const trDay = (iso: string | null | undefined) => {
  if (!iso) return '—';
  const [y, m, d] = iso.slice(0, 10).split('-');
  return `${d}.${m}.${y}`;
};

/** Hazır aralığın günleri. Bitiş en yeni kesin gündür (bugün − 3); «geçen ay» takvim ayıdır, kesinleşmemiş ucu sunucu kırpar. */
function presetRange(p: Preset, b: Bounds): { start: string; end: string } | null {
  const L = b.latest;
  if (p === 'son7') return { start: addDays(L, -6), end: L };
  if (p === 'son28') return { start: addDays(L, -27), end: L };
  if (p === 'son90') return { start: addDays(L, -89), end: L };
  if (p === 'gecenAy') {
    const today = addDays(L, 3);
    const [y, m] = today.split('-').map(Number);
    const first = new Date(Date.UTC(y, m - 2, 1)).toISOString().slice(0, 10);
    const last = new Date(Date.UTC(y, m - 1, 0)).toISOString().slice(0, 10);
    return { start: first, end: last };
  }
  return null;
}

/** Arama ve kelimeler: Search Console'daki sorgular ve sayfalar. Bütün satırlar gelir; ekran süzer ve sayfalar. */
export default function SeoSearch() {
  // Okuma/tarama/ölçüm başlatmak «SEO eşitleme ve ölçüm» ister; rolde yoksa düğme çıkmaz.
  const canRun = useCan('seo.calistir');
  const qc = useQueryClient();
  const [kind, setKind] = useState<Kind>('queries');
  const [filter, setFilter] = useState('');
  const [start, setStart] = useState(0);
  const [preset, setPreset] = useState<Preset>('kayit');
  const [custom, setCustom] = useState<{ start: string; end: string }>({ start: '', end: '' });
  const [applied, setApplied] = useState<{ start: string; end: string } | null>(null);
  const [compare, setCompare] = useState<SearchCompare | ''>('');
  // Sınırlar ilk cevapla gelir; sonraki bir aralık hata verse de seçici çalışmaya devam etsin.
  const [bounds, setBounds] = useState<Bounds | null>(null);

  const range = preset === 'kayit' ? null : preset === 'ozel' ? applied : bounds ? presetRange(preset, bounds) : null;
  const r = useQuery({
    queryKey: ['seo-search', kind, range?.start ?? '', range?.end ?? '', compare],
    queryFn: () => seoApi.search(kind, { start: range?.start, end: range?.end, compare }),
    enabled: ENGINE_ENABLED && (preset !== 'ozel' || !!applied),
    retry: false,
    placeholderData: keepPreviousData,
  });
  useEffect(() => {
    if (r.data?.bounds) setBounds(r.data.bounds);
  }, [r.data?.bounds]);
  // Aralık, tür ya da süzgeç değişince ilk sayfaya dön.
  useEffect(() => setStart(0), [kind, filter, range?.start, range?.end, compare]);

  const refresh = useMutation({
    mutationFn: seoApi.searchRefresh,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['seo-search'] });
      qc.invalidateQueries({ queryKey: ['seo-overview'] });
    },
  });

  const pick = (p: Preset) => {
    setPreset(p);
    if (p === 'ozel' && !custom.start && bounds) {
      // Özel aralık boş açılmasın: son 28 kesin gün önerilir, kişi değiştirip «Uygula»ya basar.
      setCustom({ start: addDays(bounds.latest, -27), end: bounds.latest });
    }
  };

  return (
    <SeoLayout k={r.data?.kaynaklar}
      path="/seo-geo/anahtar-kelimeler"
      crumb="Arama ve kelimeler"
      eyebrow="SEO & GEO · Google Search Console"
      title="Aranan kelimeler ve sayfalar"
      lead="İnsanların Google’da hangi kelimelerle aradığında timas.com.tr’nin çıktığı ve hangi sayfalarımızın tıklandığı. Son 28 gün her gece kaydedilir; başka bir aralık seçerseniz Search Console’dan o an okunur. Son 3 gün Google’da kesinleşmediği için dahil edilmez."
      actions={
        canRun && <button className="sg-button" onClick={() => refresh.mutate()} disabled={refresh.isPending}>
          {refresh.isPending ? <Loader2 size={16} className="animate-spin" aria-hidden /> : <RefreshCw size={16} aria-hidden />}
          Şimdi oku
        </button>
      }
    >
      {refresh.error && <Failed error={refresh.error} />}
      <div className="sg-filters" role="tablist" aria-label="Rapor">
        <button className="sg-filter" role="tab" aria-pressed={kind === 'queries'} aria-selected={kind === 'queries'} onClick={() => setKind('queries')}>
          Sorgular
        </button>
        <button className="sg-filter" role="tab" aria-pressed={kind === 'pages'} aria-selected={kind === 'pages'} onClick={() => setKind('pages')}>
          Sayfalar
        </button>
      </div>
      <p style={{ margin: '-6px 0 0', fontSize: 12.5, color: 'var(--sg-muted)' }}>
        {kind === 'queries' ? 'Google’a yazılan aramalar; en çok tıklanandan aza.' : 'Google’dan tıklama alan sayfalarımız; en çok tıklanandan aza. Adrese dokunursanız sayfa açılır.'}
      </p>

      <RangeBar
        preset={preset}
        onPreset={pick}
        bounds={bounds}
        custom={custom}
        setCustom={setCustom}
        onApply={() => setApplied({ ...custom })}
        compare={compare}
        setCompare={setCompare}
      />

      {r.isLoading && <Loading text="Search Console verisi getiriliyor…" />}
      {r.error && <Failed error={r.error} />}
      {r.data && !r.error && (
        <Table data={r.data} kind={kind} filter={filter} setFilter={setFilter} start={start} setStart={setStart} busy={r.isFetching && r.isPlaceholderData} />
      )}
    </SeoLayout>
  );
}

function RangeBar({ preset, onPreset, bounds, custom, setCustom, onApply, compare, setCompare }: {
  preset: Preset;
  onPreset: (p: Preset) => void;
  bounds: Bounds | null;
  custom: { start: string; end: string };
  setCustom: (v: { start: string; end: string }) => void;
  onApply: () => void;
  compare: SearchCompare | '';
  setCompare: (v: SearchCompare | '') => void;
}) {
  const bad = !custom.start || !custom.end || custom.start > custom.end;
  return (
    <section className="sg-range" aria-label="Tarih aralığı">
      <div className="sg-filters" role="group" aria-label="Hazır aralıklar">
        {PRESETS.map((p) => (
          <button key={p.id} type="button" className="sg-filter" aria-pressed={preset === p.id} disabled={p.id !== 'kayit' && !bounds} onClick={() => onPreset(p.id)}>
            {p.label}
          </button>
        ))}
      </div>
      <div className="sg-range-row">
        {preset === 'ozel' && (
          <form
            className="sg-range-custom"
            onSubmit={(e) => {
              e.preventDefault();
              if (!bad) onApply();
            }}
          >
            <label>
              <span>Başlangıç</span>
              <input type="date" value={custom.start} min={bounds?.earliest} max={bounds?.latest} onChange={(e) => setCustom({ ...custom, start: e.target.value })} required />
            </label>
            <label>
              <span>Bitiş</span>
              <input type="date" value={custom.end} min={bounds?.earliest} max={bounds?.latest} onChange={(e) => setCustom({ ...custom, end: e.target.value })} required />
            </label>
            <button type="submit" className="sg-button primary" disabled={bad}>
              Uygula
            </button>
          </form>
        )}
        <label className="sg-range-compare">
          <span>Karşılaştır</span>
          <select value={compare} onChange={(e) => setCompare(e.target.value as SearchCompare | '')}>
            <option value="">Karşılaştırma yok</option>
            <option value="onceki">Önceki dönemle</option>
            <option value="gecen_yil">Geçen yılın aynı günleriyle</option>
          </select>
        </label>
      </div>
      {bounds && (
        <p className="sg-range-help">
          Seçilebilen: {trDay(bounds.earliest)} – {trDay(bounds.latest)} (Google 16 aydan eskisini tutmaz, son 3 günü sonradan kesinleştirir).
          {bounds.stored ? ` Her gece kaydedilen: ${trDay(bounds.stored.start)} – ${trDay(bounds.stored.end)}.` : ' Henüz kaydedilmiş aralık yok.'}
        </p>
      )}
    </section>
  );
}

type Line = SearchRow & { prev?: SearchRow; gone?: boolean };

function Delta({ now, before, digits = 0, lowerIsBetter = false }: { now: number; before: number | undefined; digits?: number; lowerIsBetter?: boolean }) {
  if (before === undefined) return <span className="sg-delta new">yeni</span>;
  const d = now - before;
  if (Math.abs(d) < (digits ? 0.05 : 0.5)) return <span className="sg-delta">0</span>;
  const good = lowerIsBetter ? d < 0 : d > 0;
  return <span className={`sg-delta ${good ? 'up' : 'down'}`}>{d > 0 ? '+' : '−'}{fmt(Math.abs(d), digits)}</span>;
}

function Table({ data, kind, filter, setFilter, start, setStart, busy }: {
  data: SearchReport;
  kind: Kind;
  filter: string;
  setFilter: (v: string) => void;
  start: number;
  setStart: (n: number) => void;
  busy: boolean;
}) {
  const [withGone, setWithGone] = useState(false);
  const cmp = data.compare;
  const { rows, gone } = useMemo(() => {
    const f = filter.trim().toLocaleLowerCase('tr');
    const match = (r: SearchRow) => !f || r.keys[0].toLocaleLowerCase('tr').includes(f);
    const prev = new Map((cmp?.rows ?? []).map((r) => [r.keys[0], r]));
    const seen = new Set(data.rows.map((r) => r.keys[0]));
    const lines: Line[] = data.rows.filter(match).map((r) => ({ ...r, prev: cmp ? prev.get(r.keys[0]) : undefined }));
    // Önceki dönemde görünüp bu dönemde hiç görünmeyenler: sessizce kaybolmasın, sayısı yazar, istenirse listelenir.
    const goneRows: Line[] = cmp
      ? (cmp.rows ?? []).filter((r) => !seen.has(r.keys[0]) && match(r)).map((r) => ({ keys: r.keys, clicks: 0, impressions: 0, ctr: 0, position: 0, prev: r, gone: true }))
      : [];
    const all = withGone ? [...lines, ...goneRows] : lines;
    return { rows: all.sort((a, b) => b.clicks - a.clicks || (b.prev?.clicks ?? 0) - (a.prev?.clicks ?? 0)), gone: goneRows.length };
  }, [data, cmp, filter, withGone]);

  if (!data.rows.length && !cmp?.rows.length) {
    return (
      <>
        {data.notes?.map((n) => <p key={n} className="sg-banner">{n}</p>)}
        <EmptyHint
          title={data.source === 'google' ? 'Bu aralıkta Search Console verisi yok' : 'Search Console verisi yok'}
          why={data.source === 'google'
            ? 'Seçilen günlerde sitenin Google aramasında hiç görünmediği kaydedilmiş. Başka bir aralık seçin.'
            : <>Search Console bağlantısı kurulup ilk okuma yapılınca bu tablo dolar. Kurulum adımları <Link to="/seo-geo/baglantilar">Bağlantılar</Link> ekranında.</>}
        />
      </>
    );
  }
  const sum = (list: SearchRow[]) => list.reduce((a, r) => ({ c: a.c + r.clicks, i: a.i + r.impressions }), { c: 0, i: 0 });
  const totals = sum(rows.filter((r) => !r.gone));
  const prevTotals = cmp ? sum(rows.map((r) => r.prev).filter((r): r is SearchRow => !!r)) : null;
  const pct = (a: number, b: number) => (b ? `${a >= b ? '+' : '−'}%${fmt((Math.abs(a - b) / b) * 100, 1)}` : '—');
  return (
    <section className="sg-card" aria-busy={busy}>
      {data.notes?.map((n) => <p key={n} className="sg-banner" style={{ marginBottom: 10 }}>{n}</p>)}
      <p className="sg-range-shown">
        {busy && <Loader2 size={14} className="animate-spin" aria-hidden />}
        <strong>{trDay(data.start)} – {trDay(data.end)}</strong>
        <span>
          {data.source === 'google' ? `kayıtlı aralığın dışında · Search Console’dan ${dateTime(data.savedAt)} okundu` : `her gece kaydedilen veri · okundu ${dateTime(data.savedAt)}`}
        </span>
        {cmp && (
          <span>
            karşılaştırma: {COMPARE_LABEL[cmp.kind]} {trDay(cmp.start)} – {trDay(cmp.end)}
          </span>
        )}
      </p>
      <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', alignItems: 'center', marginBottom: 12 }}>
        <label className="sg-search">
          <Search size={16} aria-hidden />
          <input value={filter} onChange={(e) => setFilter(e.target.value)} placeholder={kind === 'queries' ? 'Kelime süz, ör. roman' : 'Adres süz, ör. yazar'} aria-label="Süz" />
        </label>
        <span className="sg-mono" style={{ fontSize: 12, color: 'var(--sg-muted)' }}>
          {fmt(rows.length)} satır · {fmt(totals.c)} tıklama{prevTotals ? ` (${pct(totals.c, prevTotals.c)})` : ''} · {fmt(totals.i)} gösterim{prevTotals ? ` (${pct(totals.i, prevTotals.i)})` : ''}
        </span>
        {cmp && gone > 0 && (
          <label className="sg-range-gone">
            <input type="checkbox" checked={withGone} onChange={(e) => setWithGone(e.target.checked)} />
            Bu dönemde görünmeyenleri de listele ({fmt(gone)})
          </label>
        )}
      </div>
      {!rows.length && (
        <EmptyHint
          title={filter.trim() ? 'Süzgece uyan satır yok' : 'Bu dönemde satır yok'}
          why={filter.trim() ? 'Yazdığınızı kısaltın ya da kutuyu temizleyin.' : 'Karşılaştırma dönemindeki satırları görmek için «Bu dönemde görünmeyenleri de listele»yi işaretleyin.'}
        />
      )}
      <div className="sg-table-wrap" hidden={!rows.length}>
        <table className="sg-table">
          <thead>
            <tr>
              <th>{kind === 'queries' ? 'Sorgu' : 'Sayfa'}</th>
              <th style={{ textAlign: 'right' }}><TermLabel k="clicks" label="Tıklama" /></th>
              {cmp && <th style={{ textAlign: 'right' }}>Değişim</th>}
              <th style={{ textAlign: 'right' }}><TermLabel k="impressions" label="Gösterim" /></th>
              {cmp && <th style={{ textAlign: 'right' }}>Değişim</th>}
              <th style={{ textAlign: 'right' }}><TermLabel k="ctr" label="TO" /></th>
              <th style={{ textAlign: 'right' }}><TermLabel k="position" label="Ort. sıra" /></th>
              {cmp && <th style={{ textAlign: 'right' }}>Sıra değişimi</th>}
            </tr>
          </thead>
          <tbody>
            {rows.slice(start, start + PAGE).map((r) => (
              <tr key={r.keys[0]} className={r.gone ? 'sg-row-gone' : undefined}>
                <td className={kind === 'pages' ? 'url' : ''}>
                  {kind === 'pages' ? <a href={r.keys[0]} target="_blank" rel="noreferrer">{r.keys[0].replace(/^https?:\/\/[^/]+/, '') || '/'}</a> : r.keys[0]}
                  {r.gone && <span className="sg-chip" style={{ marginLeft: 6 }}>bu dönemde yok</span>}
                </td>
                <td className="num">{fmt(r.clicks)}</td>
                {cmp && <td className="num"><Delta now={r.clicks} before={r.prev?.clicks} /></td>}
                <td className="num">{fmt(r.impressions)}</td>
                {cmp && <td className="num"><Delta now={r.impressions} before={r.prev?.impressions} /></td>}
                <td className="num">{r.gone ? '—' : `%${fmt(r.ctr * 100, 1)}`}</td>
                <td className="num">{r.gone ? '—' : fmt(r.position, 1)}</td>
                {cmp && <td className="num">{r.gone ? '—' : <Delta now={r.position} before={r.prev?.position} digits={1} lowerIsBetter />}</td>}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <SeoPager start={start} total={rows.length} size={PAGE} onChange={setStart} />
    </section>
  );
}
