import { Area, Bar, CartesianGrid, ComposedChart, Line, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { Info } from 'lucide-react';
import { InfoTip } from './InfoTip';
import { MONTHS_TR, tl } from '../lib/format';
import type { Monthly } from '../lib/metrics';

export function CashFlowChart({ monthly, live, partialMonth }: { monthly: Monthly[]; live: boolean; partialMonth?: string | null }) {
  const data = monthly.map((m) => ({
    ay: MONTHS_TR[m.month - 1],
    net: m.sales - m.returns,
    satis: m.sales,
    iade: m.returns,
    alim: m.purchases,
    fark: m.sales - m.returns - m.purchases,
  }));
  const worst = data.reduce((a, b) => (b.fark < a.fark ? b : a), data[0]);

  return (
    <section className="card min-w-0 p-5">
      <div className="flex flex-wrap items-start gap-3">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
            <h2 className="font-display text-[22px] font-semibold leading-tight">Aylık Net Ciro, Satınalma &amp; Nakit Farkı</h2>
            <InfoTip k="monthly" />
          </div>
          <p className="mt-1 text-[12px] text-ink-muted">
            Çubuk: net ciro (satış − iade). Çizgi: mal &amp; hizmet alımı. Kesik: satış iadeleri. Alan: ciro − alım farkı.
          </p>
        </div>
        <span className="chip border-brand-soft bg-brand-soft text-brand-deep">{live ? 'Canlı SQL' : 'Önbellek'} · Fatura başlığı</span>
        <div className="flex items-center gap-4 text-[11px] text-ink-muted">
          <Legend swatch="bg-brand" label="Net ciro" />
          <Legend swatch="bg-ink" label="Satınalma" line />
          <Legend swatch="bg-brand-accent" label="İade" dashed />
        </div>
      </div>

      <div className="mt-5 h-[300px]">
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={data} margin={{ top: 10, right: 12, left: 0, bottom: 0 }}>
            <defs>
              <linearGradient id="farkFill" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="#B34630" stopOpacity={0.28} />
                <stop offset="100%" stopColor="#B34630" stopOpacity={0.02} />
              </linearGradient>
            </defs>
            <CartesianGrid vertical={false} stroke="#F0E3DA" />
            <XAxis dataKey="ay" tick={{ fontSize: 11, fill: '#7C6259' }} axisLine={false} tickLine={false} />
            <YAxis tickFormatter={(v: number) => tl(v)} tick={{ fontSize: 11, fill: '#B39A90' }} axisLine={false} tickLine={false} width={64} />
            <Tooltip
              formatter={(v: number, name: string) => [tl(v, { compact: false }), name]}
              contentStyle={{ borderRadius: 12, border: '1px solid #EAD9CE', fontSize: 12 }}
              labelStyle={{ fontWeight: 700 }}
            />
            <Area type="monotone" dataKey="fark" name="Ciro − alım" fill="url(#farkFill)" stroke="none" />
            <Bar dataKey="net" name="Net ciro" fill="#E8D3C7" radius={[6, 6, 0, 0]} maxBarSize={34} />
            <Line type="monotone" dataKey="alim" name="Satınalma" stroke="#2A1912" strokeWidth={2} dot={{ r: 3, fill: '#fff', strokeWidth: 2 }} />
            <Line type="monotone" dataKey="iade" name="İade" stroke="#D64B2F" strokeWidth={2} strokeDasharray="5 4" dot={false} />
          </ComposedChart>
        </ResponsiveContainer>
      </div>

      {worst && (
        <div className="mt-4 flex items-start gap-2 rounded-xl bg-page px-3 py-2 text-[12px] text-ink-muted">
          <Info size={14} className="mt-0.5 shrink-0 text-brand" />
          <span>
            En dar ay <b className="text-ink">{worst.ay}</b>: ciro − alım farkı {tl(worst.fark)}.{partialMonth ? ` ${partialMonth} verisi kesit tarihine kadar kısmi.` : ''}
          </span>
        </div>
      )}
    </section>
  );
}

function Legend({ swatch, label, line, dashed }: { swatch: string; label: string; line?: boolean; dashed?: boolean }) {
  return (
    <span className="inline-flex items-center gap-1.5">
      <span className={`${swatch} ${line || dashed ? 'h-0.5 w-4' : 'h-3 w-1.5 rounded-sm'} ${dashed ? 'opacity-70' : ''}`} />
      {label}
    </span>
  );
}
