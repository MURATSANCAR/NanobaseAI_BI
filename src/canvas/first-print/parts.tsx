import { useState, type ReactNode } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { Area, CartesianGrid, ComposedChart, Line, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { ChevronLeft, Search } from 'lucide-react';
import Shell, { ZoomStage } from '../stitch/Shell';
import { ENGINE_ENABLED } from '../engine';
import { Pill, TableWrap, field, td, th } from '../admin/ui';
import { useDebounced } from '../editorial/kit';
import { TIER, firstPrintApi, fmtMoney, fmtUnits, monthName, pct, type AuthorHistory, type Forecast, type Horizon } from './api';
import { Explain, ExplainLabel } from '../components/Explain';

/** M10 ekranlarının ortak parçaları: çerçeve, senaryo kartları, grafik, kanal, emsal tablosu, kitap arama. */

export function FpFrame({
  crumb,
  title,
  lead,
  source,
  back,
  aside,
  children,
}: {
  crumb: string;
  title: string;
  lead?: ReactNode;
  source: string;
  back?: boolean;
  aside?: ReactNode;
  children: ReactNode;
}) {
  return (
    <Shell head={{ tenant: 'Timaş Yayınları', section: 'Fiyatlama ve üretim', crumb: 'İlk baskı tahmini', source, presence: source, detail: back ? crumb : undefined }}>
      <main className="absolute bottom-2 left-2 right-2 top-16 overflow-y-auto overscroll-contain sm:bottom-6 sm:left-6 sm:right-6 sm:top-[84px]">
        <ZoomStage>
          <div className="mx-auto flex w-full max-w-[1500px] flex-col gap-3 pb-6 lg:gap-4">
            <header className="relative z-20 flex flex-col gap-3 px-1 lg:flex-row lg:items-start lg:justify-between lg:gap-6">
              <div className="min-w-0">
                {back ? (
                  <Link to="/ilk-baski" className="inline-flex items-center gap-1 text-[11px] font-bold uppercase tracking-wide text-canvas-violet hover:underline">
                    <ChevronLeft aria-hidden className="h-3.5 w-3.5" />
                    İlk baskı tahmini
                  </Link>
                ) : (
                  <div className="text-[11px] font-bold uppercase tracking-wide text-canvas-violet">Fiyatlama ve üretim</div>
                )}
                <h1 className="mt-0.5 break-words text-[22px] font-extrabold leading-tight tracking-tight sm:text-[28px]">{title}</h1>
                {lead && <div className="mt-1 max-w-[75ch] text-[12.5px] leading-snug text-canvas-muted">{lead}</div>}
              </div>
              {aside && <div className="w-full shrink-0 lg:w-[420px]">{aside}</div>}
            </header>
            {children}
          </div>
        </ZoomStage>
      </main>
    </Shell>
  );
}

export function Box({ title, help, action, info, children }: { title?: string; help?: ReactNode; action?: ReactNode; /** Rakamların sorgu bilgisi («i»), başlığın yanında. */ info?: ReactNode; children: ReactNode }) {
  return (
    <section className="glass-panel min-w-0 rounded-2xl p-3 shadow-glass-float sm:rounded-3xl sm:p-4">
      {(title || action) && (
        <div className="mb-2 flex flex-wrap items-start justify-between gap-2">
          <div className="min-w-0">
            {title && <h2 className="flex items-center gap-1 text-[15px] font-extrabold tracking-tight">{title}{info}</h2>}
            {help && <div className="mt-0.5 text-[12px] leading-snug text-canvas-muted">{help}</div>}
          </div>
          {action}
        </div>
      )}
      {children}
    </section>
  );
}

export function TierPill({ tier }: { tier: keyof typeof TIER }) {
  const t = TIER[tier];
  return (
    <span title={t.hint}>
      <Pill tone={t.tone}>Güven: {t.label}</Pill>
    </span>
  );
}

/** Seçim düğmesi grubu (6 ay / 12 ay gibi); telefonda 44 px. */
export function Segmented<T extends string>({ value, options, onChange, label }: {
  value: T; options: Array<{ key: T; label: string }>; onChange: (v: T) => void; label: string;
}) {
  return (
    <div className="inline-grid grid-flow-col gap-1 rounded-2xl bg-slate-100 p-1" role="tablist" aria-label={label}>
      {options.map((o) => (
        <button
          key={o.key}
          type="button"
          role="tab"
          aria-selected={value === o.key}
          onClick={() => onChange(o.key)}
          className={`min-h-11 rounded-xl px-3 text-[12px] font-extrabold transition-colors duration-150 sm:min-h-9 ${
            value === o.key ? 'bg-canvas-violet text-white shadow-md' : 'text-canvas-ink hover:bg-white/70'
          }`}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

const SC_TONE: Record<string, string> = {
  kotumser: 'border-amber-200 bg-amber-50/60',
  baz: 'border-canvas-violet/40 bg-canvas-violet/5',
  iyimser: 'border-emerald-200 bg-emerald-50/60',
};

/** Üç senaryo: ilk 6 ay ve ilk 12 ay adet + ciro. */
export function ScenarioCards({ fc }: { fc: Forecast }) {
  const h6 = fc.horizons['6'];
  const h12 = fc.horizons['12'];
  return (
    <div className="grid grid-cols-1 gap-2 sm:grid-cols-3">
      {h6.scenarios.map((s, i) => {
        const s12 = h12?.scenarios[i];
        return (
          <div key={s.id} className={`rounded-2xl border p-3 ${SC_TONE[s.id]}`}>
            <div className="text-[11px] font-bold uppercase tracking-wide text-canvas-muted">{s.label}</div>
            <div className="mt-1 flex items-baseline gap-1.5">
              <span className="font-mono text-[26px] font-bold leading-none tabular-nums">{fmtUnits(s.units)}</span>
              <span className="text-[12px] font-semibold text-canvas-muted">adet · ilk 6 ay</span>
            </div>
            <div className="mt-1 text-[12px] text-canvas-muted">
              Ciro {fmtMoney(s.revenue)}
            </div>
            {s12 && (
              <div className="mt-2 border-t border-slate-200/70 pt-2 text-[12px]">
                <span className="font-mono font-bold tabular-nums">{fmtUnits(s12.units)}</span> adet · ilk 12 ay
                <span className="text-canvas-muted"> · {fmtMoney(s12.revenue)}</span>
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

type ChartRow = { label: string; band: [number, number]; base: number; pess: number; opt: number; actual?: number | null };

/** Birikimli satış: güven aralığı (gölge), baz çizgi, kötümser/iyimser kesik çizgi; çıkmış kitapta gerçekleşen. */
export function ForecastChart({ h, actual }: { h: Horizon; actual?: Forecast['actual'] }) {
  const rows: ChartRow[] = h.curve.map((c, i) => ({
    label: c.label.replace(/ (\d{4})$/, (_, y: string) => ` ${y.slice(2)}`),
    band: [c.low, c.high],
    base: c.base,
    pess: c.pess,
    opt: c.opt,
    actual: actual && i < actual.length ? actual[i].cum : null,
  }));
  return (
    <div className="h-64 w-full sm:h-72" role="img" aria-label="Birikimli satış tahmini: güven aralığı, baz, kötümser ve iyimser senaryolar">
      <ResponsiveContainer width="100%" height="100%">
        <ComposedChart data={rows} margin={{ left: 0, right: 8, top: 8, bottom: 0 }}>
          <CartesianGrid stroke="#e5e7eb" strokeDasharray="3 3" vertical={false} />
          <XAxis dataKey="label" tick={{ fontSize: 10 }} tickLine={false} axisLine={false} minTickGap={12} />
          <YAxis tick={{ fontSize: 10 }} tickLine={false} axisLine={false} width={48} tickFormatter={(v: number) => fmtUnits(v)} />
          <Tooltip
            formatter={(v: number | [number, number], name: string) =>
              Array.isArray(v) ? [`${fmtUnits(v[0])} – ${fmtUnits(v[1])}`, name] : [fmtUnits(v), name]
            }
          />
          <Area dataKey="band" name="Güven aralığı (%80)" stroke="none" fill="#7C5CFF" fillOpacity={0.12} isAnimationActive={false} />
          <Line dataKey="pess" name="Kötümser" stroke="#F59E0B" strokeDasharray="4 4" strokeWidth={1.5} dot={false} isAnimationActive={false} />
          <Line dataKey="opt" name="İyimser" stroke="#10B981" strokeDasharray="4 4" strokeWidth={1.5} dot={false} isAnimationActive={false} />
          <Line dataKey="base" name="Baz" stroke="#7C5CFF" strokeWidth={2.5} dot={false} isAnimationActive={false} />
          {actual && <Line dataKey="actual" name="Gerçekleşen" stroke="#1B1F2A" strokeWidth={2.5} dot={{ r: 3 }} connectNulls={false} isAnimationActive={false} />}
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}

export function Legend({ actual }: { actual?: boolean }) {
  const item = (cls: string, text: string) => (
    <span className="inline-flex items-center gap-1.5">
      <span aria-hidden className={cls} />
      {text}
    </span>
  );
  return (
    <div className="mt-1 flex flex-wrap gap-x-4 gap-y-1 text-[11.5px] font-semibold text-canvas-muted">
      {item('h-2.5 w-4 rounded-sm bg-canvas-violet/15', 'Güven aralığı (%80)')}
      {item('h-0.5 w-4 bg-canvas-violet', 'Baz')}
      {item('h-0.5 w-4 border-t-2 border-dashed border-canvas-amber', 'Kötümser')}
      {item('h-0.5 w-4 border-t-2 border-dashed border-canvas-mint', 'İyimser')}
      {actual && item('h-0.5 w-4 bg-canvas-ink', 'Gerçekleşen')}
    </div>
  );
}

/** Kanal dağılımı: emsallerin ilk 6 ayındaki satış payı, baz senaryonun adedine uygulanır. */
export function ChannelBars({ h }: { h: Horizon }) {
  if (!h.channels.length) return <p className="text-[12px] text-canvas-muted">Emsallerin satışında kanal bilgisi yok; kanal dağılımı gösterilemiyor.</p>;
  return (
    <ul className="space-y-1.5">
      {h.channels.map((c) => (
        <li key={c.channel} className="grid grid-cols-[minmax(0,9rem)_1fr_auto] items-center gap-2 text-[12px]">
          <span className="truncate font-semibold">{c.channel}</span>
          <span className="h-2 overflow-hidden rounded-full bg-slate-100" aria-hidden>
            <span className="block h-full rounded-full bg-canvas-violet/70" style={{ width: `${Math.max(1, c.share * 100)}%` }} />
          </span>
          <span className="whitespace-nowrap font-mono tabular-nums">
            {pct(c.share)} · {fmtUnits(c.units)}
          </span>
        </li>
      ))}
    </ul>
  );
}

export function AnalogTable({ h }: { h: Horizon }) {
  const nav = useNavigate();
  return (
    <TableWrap>
      <thead>
        <tr className="border-b border-slate-100">
          <th className={th}>Emsal kitap</th>
          <th className={th}>Çıkış</th>
          <th className={th}>Neden benzer</th>
          <th className={`${th} text-right`}>
            <span className="inline-flex items-center gap-1">
              İlk {h.curve.length} ay satış
              <Explain label="İlk aylar satışı">Emsalin çıkışından sonraki aylardaki gerçek satışı. «Düzeltilmiş» yazıyorsa, emsalin çıktığı dönemle bu kitabın dönemi arasındaki genel satış düzeyi farkına göre oranlanmış değer tahmine girer.</Explain>
            </span>
          </th>
          <th className={`${th} text-right`}>
            <ExplainLabel label="Ağırlık">Emsalin bu kitaba ne kadar benzediğini gösteren puan; puanı yüksek emsal tahmine daha çok etki eder.</ExplainLabel>
          </th>
        </tr>
      </thead>
      <tbody>
        {h.analogs.map((a) => (
          <tr key={a.code} className="border-b border-slate-50 last:border-0">
            <td className={td}>
              <button type="button" className="text-left font-bold text-canvas-ink hover:text-canvas-violet hover:underline" onClick={() => nav(`/ilk-baski/kitap/${encodeURIComponent(a.code)}`)}>
                {a.name}
              </button>
              <div className="text-[11px] text-canvas-muted">{[a.authors, a.publisher].filter(Boolean).join(' · ') || a.code}</div>
            </td>
            <td className={`${td} whitespace-nowrap`}>{monthName(a.launch)}</td>
            <td className={td}>
              <div className="flex flex-wrap gap-1">
                {a.reasons.length ? a.reasons.map((r) => <Pill key={r} tone={r === 'CRM emsali' ? 'violet' : 'muted'}>{r}</Pill>) : <span className="text-canvas-muted">genel benzerlik</span>}
              </div>
            </td>
            <td className={`${td} text-right font-mono tabular-nums`}>
              {fmtUnits(a.sales)}
              {a.factor !== 1 && <div className="text-[11px] text-canvas-muted">düzeltilmiş {fmtUnits(a.adjusted)}</div>}
            </td>
            <td className={`${td} text-right font-mono tabular-nums`}>{a.score.toLocaleString('tr-TR', { maximumFractionDigits: 2 })}</td>
          </tr>
        ))}
      </tbody>
    </TableWrap>
  );
}

/** Yazarın önceki kitapları: ilk 6 / 12 ay satışı ve tahmindeki payı (yeni kitap daha ağır). */
export function AuthorBooks({ a }: { a: AuthorHistory }) {
  const nav = useNavigate();
  return (
    <>
      <div className="mb-3 grid grid-cols-1 gap-2 sm:grid-cols-3">
        <Stat label="Yazarın tipik ilk 6 ayı" value={fmtUnits(a.level6)} hint={`${a.count} kitabın ağırlıklı düzeyi, adet`} />
        <Stat label="Yalnız emsallerden" value={fmtUnits(a.base6)} hint="yazar geçmişi olmadan ilk 6 ay, adet" />
        <Stat label="Yazar geçmişinin ağırlığı" value={pct(a.weight)} hint={`tahmin ×${a.factor.toLocaleString('tr-TR', { maximumFractionDigits: 2 })}`} />
      </div>
      <TableWrap>
        <thead>
          <tr className="border-b border-slate-100">
            <th className={th}>Kitap</th>
            <th className={th}>Çıkış</th>
            <th className={`${th} text-right`}>İlk 6 ay</th>
            <th className={`${th} text-right`}>İlk 12 ay</th>
            <th className={`${th} text-right`}>
              <ExplainLabel label="Pay">Kitabın yazar düzeyindeki payı. Yeni çıkan kitap eskisinden daha ağır sayılır.</ExplainLabel>
            </th>
          </tr>
        </thead>
        <tbody>
          {a.books.map((b) => (
            <tr key={b.code} className="border-b border-slate-50 last:border-0">
              <td className={td}>
                <button type="button" className="text-left font-bold text-canvas-ink hover:text-canvas-violet hover:underline" onClick={() => nav(`/ilk-baski/kitap/${encodeURIComponent(b.code)}`)}>
                  {b.name}
                </button>
              </td>
              <td className={`${td} whitespace-nowrap`}>{monthName(b.launch)}</td>
              <td className={`${td} text-right font-mono tabular-nums`}>{fmtUnits(b.sales6)}</td>
              <td className={`${td} text-right font-mono tabular-nums`}>{b.sales12 !== null ? fmtUnits(b.sales12) : <span className="text-canvas-muted">dolmadı</span>}</td>
              <td className={`${td} text-right font-mono tabular-nums`}>{pct(b.weight)}</td>
            </tr>
          ))}
        </tbody>
      </TableWrap>
    </>
  );
}

function Stat({ label, value, hint }: { label: string; value: string; hint: string }) {
  return (
    <div className="min-w-0 rounded-xl border border-slate-100 bg-white/70 p-2.5">
      <div className="truncate text-[11px] font-bold uppercase tracking-wide text-canvas-muted">{label}</div>
      <div className="mt-0.5 font-mono text-[20px] font-bold leading-tight tabular-nums">{value}</div>
      <div className="text-[11px] leading-snug text-canvas-muted">{hint}</div>
    </div>
  );
}

/** CRM'deki herhangi bir kitabı arar (ad, yazar, yayınevi, stok kodu); seçilen kitabın tahmini açılır. */
export function BookSearch({ onPick, placeholder = 'Kitap ara: ad, yazar ya da stok kodu' }: { onPick?: (code: string) => void; placeholder?: string }) {
  const [q, setQ] = useState('');
  const dq = useDebounced(q.trim(), 250);
  const nav = useNavigate();
  const res = useQuery({ queryKey: ['first-print', 'books', dq], queryFn: () => firstPrintApi.books(dq), enabled: ENGINE_ENABLED && dq.length >= 2, staleTime: 60_000 });
  const pick = (code: string) => {
    setQ('');
    if (onPick) onPick(code);
    else nav(`/ilk-baski/kitap/${encodeURIComponent(code)}`);
  };
  return (
    <div className="relative">
      <label className="relative block">
        <span className="sr-only">{placeholder}</span>
        <Search aria-hidden className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-canvas-muted" />
        <input type="search" value={q} onChange={(e) => setQ(e.target.value)} placeholder={placeholder} className={`${field} min-h-11 pl-9`} />
      </label>
      {dq.length >= 2 && (
        <div className="absolute left-0 right-0 top-full z-30 mt-1 max-h-80 overflow-y-auto overscroll-contain rounded-2xl border border-slate-100 bg-white p-1 shadow-canvas-card">
          {res.isLoading && <p className="px-3 py-2 text-[12px] text-canvas-muted">Aranıyor…</p>}
          {res.error && <p className="px-3 py-2 text-[12px] text-red-700">{(res.error as Error).message}</p>}
          {res.data && res.data.items.length === 0 && <p className="px-3 py-2 text-[12px] text-canvas-muted">Eşleşen kitap yok. Adın bir kısmını, yazarı ya da stok kodunu deneyin.</p>}
          {res.data && res.data.items.length > 0 && (
            <p className="px-3 pb-1 pt-1.5 text-[11px] font-bold uppercase tracking-wide text-canvas-muted">{fmtUnits(res.data.total)} kitap</p>
          )}
          {res.data?.items.map((b) => (
            <button key={b.code} type="button" onClick={() => pick(b.code)} className="flex min-h-11 w-full flex-col items-start rounded-xl px-3 py-1.5 text-left hover:bg-slate-50">
              <span className="text-[12.5px] font-bold">{b.name}</span>
              <span className="text-[11px] text-canvas-muted">
                {[b.authors, b.publisher, b.launched ? 'çıktı' : b.firstPub ? `yayın ${b.firstPub.slice(0, 7)}` : 'yayın tarihi yok'].filter(Boolean).join(' · ')}
              </span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
