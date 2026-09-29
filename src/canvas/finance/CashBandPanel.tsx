import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { AlertTriangle } from 'lucide-react';
import { Note, Pill } from '../admin/ui';
import { Panel } from '../editorial/kit';
import { fmtDay, fmtMoney, fmtShort, type CashBand } from './api';
import SqlInfo from '../components/SqlInfo';
import type { Kaynaklar } from '../components/sqlInfo';
import { Explain } from '../components/Explain';

/** Olasılıklı 13 haftalık nakit bandı (öneri 7). Vadesi belli kalemler (çek/senet, sözleşme ödemesi, vergi) tablodaki
 *  kuraldan; vadesi belirsiz müşteri tahsilatı ve satıcı ödemesi geçmiş haftalık gerçekleşenin tahmininden (p10–p90).
 *  «En kötü %10» çizgisi = kesin kalemler + tahsilat p10 − ödeme p90. Kantil yoksa bant hiç çizilmez. */
export default function CashBandPanel({ band, k }: { band: CashBand | undefined; k?: Kaynaklar }) {
  if (!band) return null;
  if (!band.var) {
    return (
      <Panel>
        <div className="flex flex-wrap items-center gap-2">
          <h3 className="text-[15px] font-extrabold">Olasılıklı nakit bandı</h3>
          <Pill tone="muted">Tahmin yok</Pill>
        </div>
        <p className="mt-1 text-[12.5px] text-canvas-muted">{band.neden} Tablo kurala göre (vadelerden) kalır.</p>
      </Panel>
    );
  }
  const data = band.haftalar.map((w) => ({
    ad: `${w.hafta}.`, 'En kötü %10': w.kapanis.kotu, Beklenen: w.kapanis.orta, 'En iyi %10': w.kapanis.iyi, 'Vadelere göre': w.kuralKapanis,
  }));
  const last = band.haftalar.at(-1);
  return (
    <Panel>
      <div className="flex flex-wrap items-center gap-2">
        <h3 className="flex items-center gap-1 text-[15px] font-extrabold">
          Olasılıklı nakit bandı
          <Explain label="Olasılıklı nakit bandı">
            Günü belli olan kalemler (çek-senet, sözleşme ödemesi, vergi) olduğu gibi alınır; günü belirsiz müşteri tahsilatı ve satıcı ödemesi için geçmiş haftaların gerçekleşeninden bir aralık çıkarılır. «En kötü %10»: yalnız on durumdan birinde bundan kötü olması beklenir; «En iyi %10» bunun tersidir.
          </Explain>
          <SqlInfo k={k} alan="bant" label="Olasılıklı nakit bandı" />
        </h3>
        <Pill tone="violet">Tahmin</Pill>
      </div>
      <p className="mt-1 text-[12px] leading-snug text-canvas-muted">{band.not} Geçmiş: {band.gecmisHafta} hafta.</p>
      {band.enKotuAcik && (
        <div className="mt-2 flex items-start gap-2 rounded-2xl bg-amber-50 px-3 py-2 text-[12.5px] font-semibold text-amber-900">
          <AlertTriangle aria-hidden className="mt-0.5 h-4 w-4 shrink-0" />
          <span>
            En kötü %10 senaryoda {band.enKotuAcik.hafta}. hafta ({fmtDay(band.enKotuAcik.baslangic)}) kasa {fmtMoney(band.enKotuAcik.kapanis)}: açık riski.
            <SqlInfo k={k} alan="bant" label="En kötü %10 senaryoda açık" className="ml-0.5" />
          </span>
        </div>
      )}
      {last && (
        <div className="mt-2 grid grid-cols-3 gap-2 text-[12px]">
          {([['En kötü %10', last.kapanis.kotu], ['Beklenen', last.kapanis.orta], ['En iyi %10', last.kapanis.iyi]] as const).map(([name, v]) => (
            <div key={name} className="rounded-xl bg-white/80 p-2">
              <div className="flex items-center gap-0.5 text-[10.5px] font-bold uppercase text-canvas-muted">{name}<SqlInfo k={k} alan="bant" label={`${name} · 13. hafta sonu`} /></div>
              <div className={`font-mono text-[14px] font-bold tabular-nums ${v < 0 ? 'text-red-700' : ''}`}>{fmtShort(v)}</div>
              <div className="text-[10.5px] text-canvas-muted">13. hafta sonu</div>
            </div>
          ))}
        </div>
      )}
      <div className="mt-3 h-[220px] w-full sm:h-[260px]">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={data} margin={{ top: 4, right: 4, left: 0, bottom: 0 }}>
            <CartesianGrid vertical={false} stroke="#e2e8f0" />
            <XAxis dataKey="ad" tick={{ fontSize: 11 }} tickLine={false} axisLine={false} />
            <YAxis tickFormatter={(v: number) => fmtShort(v)} tick={{ fontSize: 11 }} width={56} tickLine={false} axisLine={false} />
            <Tooltip formatter={(v) => (typeof v === 'number' ? fmtMoney(v) : '—')} />
            <Legend wrapperStyle={{ fontSize: 11 }} />
            <Line dataKey="En kötü %10" stroke="#dc2626" strokeWidth={2} dot={false} isAnimationActive={false} />
            <Line dataKey="Beklenen" stroke="#6d28d9" strokeWidth={2} dot={false} isAnimationActive={false} />
            <Line dataKey="En iyi %10" stroke="#16a34a" strokeWidth={1.5} dot={false} isAnimationActive={false} />
            <Line dataKey="Vadelere göre" stroke="#64748b" strokeDasharray="4 3" strokeWidth={1.5} dot={false} isAnimationActive={false} />
          </LineChart>
        </ResponsiveContainer>
      </div>
      <Note tone="info">Bant haftalık aralıkların toplamıdır; gerçek belirsizlik bundan dardır, temkinli okunur. «Vadelere göre» çizgisi yukarıdaki tablonun kapanışıdır.</Note>
    </Panel>
  );
}
