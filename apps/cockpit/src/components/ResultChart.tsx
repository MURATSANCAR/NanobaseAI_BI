/**
 * Copilot sonucunun grafiğe dönüşü.
 *
 * Grafik tipi kararı burada verilmez — köprü, `backend/nanobase_api/chat_widgets.py` ile
 * (ana uygulamayla ortak, deterministik, LLM'siz) bir BiWidget spec'i döndürür. Bu dosya
 * yalnızca o spec'i cockpit'in kendi paleti ve sayı biçimiyle çizer.
 * Desteklenmeyen tip (table vb.) → null; panel mevcut tablosuna düşer.
 */
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
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
  return num(n);
}

/** Eksen/etiket için kısa, tooltip için tam gösterim. */
function fmt(key: string | undefined, v: unknown, short = false): string {
  const n = toNum(v);
  if (n == null) return v == null ? '' : String(v);
  if (isMoney(key)) return tl(n, { compact: short });
  return short ? compact(n) : num(n);
}

function truncate(v: unknown, max: number): string {
  const s = v == null ? '' : String(v);
  return s.length > max ? `${s.slice(0, max - 1)}…` : s;
}

export function ResultChart({
  widget,
  records,
  wide,
}: {
  widget: WidgetSpec;
  records: Record<string, unknown>[];
  wide?: boolean;
}) {
  const h = wide ? 220 : 172;

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
        <div className={`grid gap-2 ${cards.length > 2 ? 'grid-cols-3' : 'grid-cols-2'}`}>
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

  const limit = widget.type === 'pie' ? 8 : wide ? 16 : 8;
  // Alan adları `x`/`y` OLAMAZ: Recharts nokta koordinatlarını aynı adlarla yazıyor ve
  // seri tek bir x'e çöküyor (line path'i M46,…C46,… çıkar). `cat`/`val` ile çakışma yok.
  const data = records
    .map((r) => ({ cat: r[xk], val: toNum(r[yk]) }))
    .filter((d): d is { cat: unknown; val: number } => d.val != null)
    .slice(0, limit);
  if (data.length < 2) return null;

  const cut = records.length > data.length ? `İlk ${data.length} / ${records.length}` : null;
  const tip = (v: unknown) => [fmt(yk, v), yk] as [string, string];

  if (widget.type === 'line') {
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

  if (widget.type === 'pie') {
    return (
      <Frame note={cut}>
        <ResponsiveContainer width="100%" height={h}>
          <PieChart margin={{ top: 4, right: 4, left: 4, bottom: 4 }}>
            <Pie
              data={data}
              dataKey="val"
              nameKey="cat"
              innerRadius="45%"
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

function Frame({ children, note }: { children: React.ReactNode; note?: string | null }) {
  return (
    <div className="mt-2 rounded-lg border border-line bg-white p-2">
      {children}
      {note && <div className="mt-1 text-right text-[10px] text-ink-faint">{note}</div>}
    </div>
  );
}
