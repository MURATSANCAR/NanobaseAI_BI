/**
 * Copilot sonucunun grafiğe dönüşü.
 *
 * Grafik tipi kararı burada verilmez — köprü, `backend/nanobase_api/chat_widgets.py` ile
 * (ana uygulamayla ortak, deterministik, LLM'siz) bir BiWidget spec'i döndürür. Bu dosya
 * yalnızca o spec'i cockpit'in kendi paleti ve sayı biçimiyle çizer.
 * Desteklenmeyen tip (table vb.) → null; panel mevcut tablosuna düşer.
 */
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Line,
  LineChart,
  Pie,
  PieChart,
  RadialBar,
  RadialBarChart,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip,
  Treemap,
  XAxis,
  YAxis,
  ZAxis,
} from 'recharts';
import type { WidgetSpec } from '../lib/engine';
import { num, tl } from '../lib/format';

// tailwind.config.js ile aynı: brand, ink, warn, ok — ek seri rengi icat edilmedi.
const SERIES = ['#B34630', '#2A1912', '#C98A1E', '#3C7D4E', '#8F3521', '#7C6259', '#D64B2F', '#B39A90'];
const TICK = { fontSize: 10, fill: '#7C6259' };
const GRID = '#F0E3DA';
const TOOLTIP = { borderRadius: 12, border: '1px solid #EAD9CE', fontSize: 11 } as const;
// Sohbet cevabı anında okunmalı; giriş animasyonu hem gecikme katıyor hem yeniden-render'da baştan
// tetiklenip grafiği boş gösteriyor — tüm serilerde isAnimationActive={false}.

/** Para gibi okunan ölçüler ₺ ile gösterilir. Oran/adet alanları hariç tutulur;
 *  yanlış tahminin bedeli yalnızca ₺ işaretidir, veri değişmez. */
const MONEY = /(tutar|ciro|maliyet|bakiye|fiyat|kar|kâr|gelir|gider|satis|satış|iade|alim|alım)/i;
const NOT_MONEY = /(oran|yuzde|yüzde|adet|sayi|sayı|count|miktar|gun|gün)/i;

const nf1 = new Intl.NumberFormat('tr-TR', { maximumFractionDigits: 1 });
// Preserve fractional measures; rounding a ratio to an integer makes distinct
// axis ticks (and tooltip values) appear identical.
const preciseNumber = new Intl.NumberFormat('tr-TR', { maximumSignificantDigits: 6 });
const measureNumber = (n: number) => Number.isInteger(n) ? num(n) : preciseNumber.format(n);

function isMoney(key?: string): boolean {
  return !!key && MONEY.test(key) && !NOT_MONEY.test(key);
}

function toNum(v: unknown): number | null {
  if (typeof v === 'number') return Number.isFinite(v) ? v : null;
  if (typeof v === 'string') {
    const n = Number(v.trim().replace(/,/g, ''));
    return v.trim() && Number.isFinite(n) ? n : null;
  }
  return null;
}

function compact(n: number): string {
  const a = Math.abs(n);
  if (a >= 1e9) return `${nf1.format(n / 1e9)}Mr`;
  if (a >= 1e6) return `${nf1.format(n / 1e6)}M`;
  if (a >= 1e4) return `${nf1.format(n / 1e3)}B`;
  return measureNumber(n);
}

/** Eksen/etiket için kısa, tooltip için tam gösterim. */
function formatMeasure(key: string | undefined, v: unknown, short = false, plainNumber = false): string {
  const n = toNum(v);
  if (n == null) return v == null ? '' : String(v);
  if (!plainNumber && isMoney(key)) return tl(n, { compact: short });
  return short ? compact(n) : measureNumber(n);
}

function truncate(v: unknown, max: number): string {
  const s = v == null ? '' : String(v);
  return s.length > max ? `${s.slice(0, max - 1)}…` : s;
}

/** Bir sonucun hangi biçimlerde okunabileceği.
 *
 *  Köprü şeklinden bir tip seçiyor ve çoğu zaman doğru seçiyor, ama "doğru" grafik sorunun
 *  cevabında değil soranın kafasında: aynı sekiz satır kimine pay (halka), kimine sıralama
 *  (çubuk), kimine katkı (şelale) olarak lazım. `fits` yalnızca verinin izin verdiklerini
 *  gösterir — okunamayacak bir tipi teklif etmek, seçenek değil tuzaktır. */
export type ChartKind =
  | 'bar' | 'column' | 'line' | 'area' | 'pie' | 'donut'
  | 'waterfall' | 'scatter' | 'treemap' | 'gauge' | 'table';

export const CHART_LABEL: Record<ChartKind, string> = {
  bar: 'yatay çubuk', column: 'dikey sütun', line: 'çizgi', area: 'alan',
  pie: 'pasta', donut: 'halka', waterfall: 'şelale', scatter: 'dağılım',
  treemap: 'ağaç haritası', gauge: 'gösterge', table: 'tablo',
};

/** Bu veri şeklinde hangi tipler okunur. */
export function chartOptions(records: Record<string, unknown>[], widget: WidgetSpec): ChartKind[] {
  const xk = widget.x_key;
  const yk = widget.y_key;
  if (!xk || !yk) return [];
  const rows = records.filter((r) => toNum(r[yk]) != null);
  if (rows.length < 2) return [];
  const out: ChartKind[] = ['bar', 'column', 'line', 'area', 'table'];
  // Pay grafikleri yalnız aynı işaretli ve az sayıda kategoride anlamlı: negatif dilim çizilemez,
  // yirmi dilim okunamaz.
  const vals = rows.map((r) => toNum(r[yk]) as number);
  if (rows.length <= 12 && vals.every((v) => v >= 0)) out.push('pie', 'donut', 'treemap');
  out.push('waterfall');
  if (rows.every((r) => toNum(r[xk]) != null)) out.push('scatter');
  if (rows.length <= 6 && vals.every((v) => v >= 0)) out.push('gauge');
  return out;
}

export function ResultChart({
  widget,
  records,
  wide,
  chart,
  height,
}: {
  widget: WidgetSpec;
  records: Record<string, unknown>[];
  wide?: boolean;
  /** Kişinin seçtiği tip; verilmezse köprünün seçtiği kullanılır. */
  chart?: ChartKind;
  height?: number;
}) {
  const h = height ?? (wide ? 220 : 172);
  const fmt = (key: string | undefined, v: unknown, short = false) =>
    formatMeasure(key, v, short, widget.format === 'number'
      && (key === widget.y_key || key === widget.value_key));

  if (widget.type === 'kpi') {
    const k = widget.value_key;
    const v = k ? records[0]?.[k] : undefined;
    if (toNum(v) == null) return null;
    return (
      <Frame>
        <div className="px-1 py-2">
          <div className="font-display text-[26px] font-semibold leading-none text-ink">{fmt(k, v)}</div>
          <div className="mt-1.5 text-[11px] text-ink-muted">{k}</div>
        </div>
      </Frame>
    );
  }

  if (widget.type === 'multi_card') {
    // multi_card satırları sonuç setinde yok — köprü bu tipte `data` bloğunu koruyor.
    const rows = widget.data?.rows ?? [];
    const lk = widget.label_key ?? 'label';
    const vk = widget.value_key ?? 'value';
    const cards = rows.filter((r) => toNum(r[vk]) != null);
    if (cards.length === 0) return null;
    return (
      <Frame>
        <div className={`grid gap-2 ${cards.length > 2 ? 'grid-cols-1 sm:grid-cols-3' : 'grid-cols-1 sm:grid-cols-2'}`}>
          {cards.map((r, i) => (
            <div key={i} className="rounded-lg bg-page px-2 py-1.5">
              <div className="truncate text-[10px] text-ink-muted" title={String(r[lk])}>{String(r[lk])}</div>
              <div className="mt-0.5 font-display text-[14px] font-semibold leading-tight text-ink">
                {fmt(String(r[lk]), r[vk], true)}
              </div>
            </div>
          ))}
        </div>
      </Frame>
    );
  }

  const xk = widget.x_key;
  const yk = widget.y_key;
  if (!xk || !yk) return null;

  const kind = (chart ?? widget.type) as ChartKind;
  const limit = kind === 'pie' || kind === 'donut' || kind === 'gauge' ? 8 : wide ? 16 : 12;
  // Alan adları `x`/`y` OLAMAZ: Recharts nokta koordinatlarını aynı adlarla yazıyor ve
  // seri tek bir x'e çöküyor (line path'i M46,…C46,… çıkar). `cat`/`val` ile çakışma yok.
  const data = records
    .map((r) => ({ cat: r[xk], val: toNum(r[yk]) }))
    .filter((d): d is { cat: unknown; val: number } => d.val != null)
    .slice(0, limit);
  if (data.length < 2) return null;

  const cut = records.length > data.length ? `İlk ${data.length} / ${records.length}` : null;
  const tip = (v: unknown) => [fmt(yk, v), yk] as [string, string];

  if (kind === 'line') {
    return (
      <Frame note={cut}>
        <ResponsiveContainer width="100%" height={h}>
          <LineChart data={data} margin={{ top: 6, right: 8, left: 0, bottom: 0 }}>
            <CartesianGrid vertical={false} stroke={GRID} />
            <XAxis dataKey="cat" tick={TICK} axisLine={false} tickLine={false} tickFormatter={(v) => truncate(v, 8)} />
            <YAxis tick={TICK} axisLine={false} tickLine={false} width={46} tickFormatter={(v) => fmt(yk, v, true)} />
            <Tooltip formatter={tip} contentStyle={TOOLTIP} labelStyle={{ fontWeight: 700 }} />
            <Line type="monotone" dataKey="val" name={yk} stroke={SERIES[0]} strokeWidth={2} dot={{ r: 2.5, fill: '#fff', strokeWidth: 2 }} isAnimationActive={false} />
          </LineChart>
        </ResponsiveContainer>
      </Frame>
    );
  }

  if (kind === 'pie' || kind === 'donut') {
    return (
      <Frame note={cut}>
        <ResponsiveContainer width="100%" height={h}>
          <PieChart margin={{ top: 4, right: 4, left: 4, bottom: 4 }}>
            <Pie
              data={data}
              dataKey="val"
              nameKey="cat"
              innerRadius={kind === "donut" ? "52%" : 0}
              outerRadius="78%"
              paddingAngle={2}
              stroke="#fff"
              strokeWidth={2}
              isAnimationActive={false}
            >
              {data.map((_, i) => <Cell key={i} fill={SERIES[i % SERIES.length]} />)}
            </Pie>
            <Tooltip formatter={tip} contentStyle={TOOLTIP} />
          </PieChart>
        </ResponsiveContainer>
        <ul className="mt-1.5 flex flex-wrap gap-x-3 gap-y-1 text-[10px] text-ink-muted">
          {data.map((d, i) => (
            <li key={i} className="inline-flex items-center gap-1">
              <span className="h-2 w-2 rounded-sm" style={{ background: SERIES[i % SERIES.length] }} />
              {truncate(d.cat, 18)}
            </li>
          ))}
        </ul>
      </Frame>
    );
  }

  if (kind === 'area') {
    return (
      <Frame note={cut}>
        <ResponsiveContainer width="100%" height={h}>
          <AreaChart data={data} margin={{ top: 6, right: 8, left: 0, bottom: 0 }}>
            <defs>
              <linearGradient id="rc-area" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor={SERIES[0]} stopOpacity={0.35} />
                <stop offset="100%" stopColor={SERIES[0]} stopOpacity={0.02} />
              </linearGradient>
            </defs>
            <CartesianGrid vertical={false} stroke={GRID} />
            <XAxis dataKey="cat" tick={TICK} axisLine={false} tickLine={false} tickFormatter={(v) => truncate(v, 8)} />
            <YAxis tick={TICK} axisLine={false} tickLine={false} width={46} tickFormatter={(v) => fmt(yk, v, true)} />
            <Tooltip formatter={tip} contentStyle={TOOLTIP} labelStyle={{ fontWeight: 700 }} />
            <Area type="monotone" dataKey="val" name={yk} stroke={SERIES[0]} strokeWidth={2} fill="url(#rc-area)" isAnimationActive={false} />
          </AreaChart>
        </ResponsiveContainer>
      </Frame>
    );
  }

  if (kind === 'column') {
    return (
      <Frame note={cut}>
        <ResponsiveContainer width="100%" height={h}>
          <BarChart data={data} margin={{ top: 6, right: 8, left: 0, bottom: 0 }}>
            <CartesianGrid vertical={false} stroke={GRID} />
            <XAxis dataKey="cat" tick={TICK} axisLine={false} tickLine={false} interval={0}
                   angle={data.length > 6 ? -25 : 0} textAnchor={data.length > 6 ? 'end' : 'middle'}
                   height={data.length > 6 ? 42 : 24} tickFormatter={(v) => truncate(v, 10)} />
            <YAxis tick={TICK} axisLine={false} tickLine={false} width={46} tickFormatter={(v) => fmt(yk, v, true)} />
            <Tooltip formatter={tip} contentStyle={TOOLTIP} labelStyle={{ fontWeight: 700 }} cursor={{ fill: '#F4DCD3', opacity: 0.4 }} />
            <Bar dataKey="val" name={yk} fill={SERIES[0]} radius={[5, 5, 0, 0]} maxBarSize={34} isAnimationActive={false} />
          </BarChart>
        </ResponsiveContainer>
      </Frame>
    );
  }

  if (kind === 'waterfall') {
    // Her çubuk bir öncekinin bittiği yerden başlar: sıralı katkının nasıl toplandığını gösterir.
    // Taban görünmez bir çubuk, üstündeki gerçek katkı — artı ve eksi ayrı renk.
    let run = 0;
    const wf = data.map((d) => {
      const base = d.val >= 0 ? run : run + d.val;
      run += d.val;
      return { cat: d.cat, base, delta: Math.abs(d.val), val: d.val, total: run };
    });
    return (
      <Frame note={cut}>
        <ResponsiveContainer width="100%" height={h}>
          <BarChart data={wf} margin={{ top: 6, right: 8, left: 0, bottom: 0 }} stackOffset="sign">
            <CartesianGrid vertical={false} stroke={GRID} />
            <XAxis dataKey="cat" tick={TICK} axisLine={false} tickLine={false} interval={0}
                   angle={wf.length > 6 ? -25 : 0} textAnchor={wf.length > 6 ? 'end' : 'middle'}
                   height={wf.length > 6 ? 42 : 24} tickFormatter={(v) => truncate(v, 10)} />
            <YAxis tick={TICK} axisLine={false} tickLine={false} width={46} tickFormatter={(v) => fmt(yk, v, true)} />
            <Tooltip contentStyle={TOOLTIP} labelStyle={{ fontWeight: 700 }}
                     formatter={(_v, _n, p) => {
                       const r = (p as { payload?: { val: number; total: number } }).payload;
                       return r ? [`${fmt(yk, r.val)} → ${fmt(yk, r.total)}`, 'katkı → birikim'] : ['', ''];
                     }} />
            <Bar dataKey="base" stackId="w" fill="transparent" isAnimationActive={false} />
            <Bar dataKey="delta" stackId="w" radius={[4, 4, 0, 0]} maxBarSize={34} isAnimationActive={false}>
              {wf.map((r, i) => <Cell key={i} fill={r.val >= 0 ? SERIES[3] : SERIES[0]} />)}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </Frame>
    );
  }

  if (kind === 'scatter') {
    const pts = data.map((d) => ({ x: toNum(d.cat) as number, y: d.val })).filter((p) => p.x != null);
    return (
      <Frame note={cut}>
        <ResponsiveContainer width="100%" height={h}>
          <ScatterChart margin={{ top: 8, right: 10, left: 0, bottom: 4 }}>
            <CartesianGrid stroke={GRID} />
            <XAxis type="number" dataKey="x" name={xk} tick={TICK} axisLine={false} tickLine={false} tickFormatter={(v) => fmt(xk, v, true)} />
            <YAxis type="number" dataKey="y" name={yk} tick={TICK} axisLine={false} tickLine={false} width={46} tickFormatter={(v) => fmt(yk, v, true)} />
            <ZAxis range={[40, 40]} />
            <Tooltip contentStyle={TOOLTIP} cursor={{ strokeDasharray: '3 3' }}
                     formatter={(v, n) => [fmt(n === xk ? xk : yk, v), String(n)]} />
            <Scatter data={pts} fill={SERIES[0]} isAnimationActive={false} />
          </ScatterChart>
        </ResponsiveContainer>
      </Frame>
    );
  }

  if (kind === 'treemap') {
    const tm = data.map((d, i) => ({ name: truncate(d.cat, 18), size: Math.abs(d.val), fill: SERIES[i % SERIES.length] }));
    return (
      <Frame note={cut}>
        <ResponsiveContainer width="100%" height={h}>
          <Treemap data={tm} dataKey="size" stroke="#fff" isAnimationActive={false} content={<TreemapCell />}>
            <Tooltip formatter={(v) => [fmt(yk, v), yk] as [string, string]} contentStyle={TOOLTIP} />
          </Treemap>
        </ResponsiveContainer>
      </Frame>
    );
  }

  if (kind === 'gauge') {
    // Her kategori bir halka; en büyüğü tam tur. Hedef yoksa ölçek verinin kendisidir ve bu
    // grafiğin söyleyebileceği tek şey oran — o yüzden rakam da yazılıyor.
    const max = Math.max(...data.map((d) => d.val));
    const rings = data.map((d, i) => ({ name: truncate(d.cat, 16), val: d.val,
                                        pct: max ? (d.val / max) * 100 : 0, fill: SERIES[i % SERIES.length] }));
    return (
      <Frame note={cut}>
        <ResponsiveContainer width="100%" height={h}>
          <RadialBarChart data={rings} innerRadius="30%" outerRadius="95%" startAngle={200} endAngle={-20}>
            <RadialBar dataKey="pct" background={{ fill: '#F6F3F0' }} cornerRadius={6} isAnimationActive={false} />
            <Tooltip contentStyle={TOOLTIP}
                     formatter={(_v, _n, p) => {
                       const r = (p as { payload?: { name: string; val: number } }).payload;
                       return r ? [fmt(yk, r.val), r.name] : ['', ''];
                     }} />
          </RadialBarChart>
        </ResponsiveContainer>
        <ul className="mt-1 flex flex-wrap gap-x-3 gap-y-1 text-[10px] text-ink-muted">
          {rings.map((r, i) => (
            <li key={i} className="inline-flex items-center gap-1">
              <span className="h-2 w-2 rounded-sm" style={{ background: r.fill }} />
              {r.name} · {fmt(yk, r.val, true)}
            </li>
          ))}
        </ul>
      </Frame>
    );
  }

  if (kind === 'table') {
    return (
      <Frame note={cut}>
        <div className="max-h-64 overflow-auto">
          <table className="w-full text-[11px]">
            <thead className="sticky top-0 bg-white">
              <tr className="border-b border-line text-left text-ink-muted">
                <th className="py-1 pr-2 font-medium">{xk}</th>
                <th className="py-1 text-right font-medium">{yk}</th>
              </tr>
            </thead>
            <tbody className="tabular-nums">
              {data.map((d, i) => (
                <tr key={i} className="border-b border-line/60 last:border-0">
                  <td className="py-1 pr-2">{truncate(d.cat, 40)}</td>
                  <td className="py-1 text-right">{fmt(yk, d.val)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Frame>
    );
  }

  // bar — kırılımlar uzun adlar üretir (müşteri, kitap, yayınevi); yatay çubuk okunur kalır.
  return (
    <Frame note={cut}>
      {/* Kategori adları iki satıra sarabiliyor: satır yüksekliği buna göre; aksi halde etiketler çakışıyor. */}
      <ResponsiveContainer width="100%" height={Math.max(h, data.length * (wide ? 26 : 30) + 24)}>
        <BarChart data={data} layout="vertical" margin={{ top: 2, right: 10, left: 0, bottom: 0 }}>
          <CartesianGrid horizontal={false} stroke={GRID} />
          <XAxis type="number" tick={TICK} axisLine={false} tickLine={false} tickFormatter={(v) => fmt(yk, v, true)} />
          <YAxis
            type="category"
            dataKey="cat"
            tick={TICK}
            axisLine={false}
            tickLine={false}
            width={wide ? 120 : 96}
            interval={0}
            tickFormatter={(v) => truncate(v, wide ? 18 : 16)}
          />
          <Tooltip formatter={tip} contentStyle={TOOLTIP} labelStyle={{ fontWeight: 700 }} cursor={{ fill: '#F4DCD3', opacity: 0.4 }} />
          <Bar dataKey="val" name={yk} fill={SERIES[0]} radius={[0, 5, 5, 0]} maxBarSize={16} isAnimationActive={false} />
        </BarChart>
      </ResponsiveContainer>
    </Frame>
  );
}

/** Treemap kutusu: recharts'ın kendi içeriği rengi ve etiketi taşımıyor. */
function TreemapCell(props: unknown) {
  const p = props as { x: number; y: number; width: number; height: number; name?: string; fill?: string };
  const show = p.width > 52 && p.height > 22;
  return (
    <g>
      <rect x={p.x} y={p.y} width={p.width} height={p.height} fill={p.fill ?? SERIES[0]} stroke="#fff" strokeWidth={2} rx={4} />
      {show && (
        <text x={p.x + 6} y={p.y + 15} fill="#fff" fontSize={10} fontWeight={600}>
          {truncate(p.name, Math.floor(p.width / 6.5))}
        </text>
      )}
    </g>
  );
}

function Frame({ children, note }: { children: React.ReactNode; note?: string | null }) {
  return (
    <div className="mt-2 rounded-lg border border-line bg-white p-2">
      {children}
      {note && <div className="mt-1 text-right text-[10px] text-ink-faint">{note}</div>}
    </div>
  );
}
