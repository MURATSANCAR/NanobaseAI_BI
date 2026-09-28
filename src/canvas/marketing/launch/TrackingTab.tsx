import { useQuery } from '@tanstack/react-query';
import { CartesianGrid, Legend, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { ENGINE_ENABLED } from '../../engine';
import { Loading, Note, TableWrap, errText, td, th } from '../../admin/ui';
import { fmtDay, fmtInt, fmtMoney, fmtPct } from '../api';
import { Block } from '../parts';
import SqlInfo, { InfoLabel } from '../../components/SqlInfo';
import type { Kaynaklar } from '../../components/sqlInfo';
import { dLabel, launchApi, type Depot, type Launch, type LaunchMeta } from './api';

/** İzleme (ilk 7 / 30 gün): birikimli sipariş (CRM, canlı), faturalı satış (Logo, veri sonuna kadar), hedef payı ve emsal
 *  ortalaması aynı grafikte; rafa ulaşma (dağılım, açık sipariş, bekleyen ürün, depo) ayrı kutularda. Sipariş satış
 *  değildir; iki çizgi ayrı renk ve adla. Donmuş Logo verisi her zaman veri sonu tarihiyle gösterilir. */

const SERIES = [
  { key: 'siparisKum', name: 'Sipariş (CRM)', color: '#0ea5e9' },
  { key: 'faturaKum', name: 'Faturalı satış (Logo)', color: '#6d28d9' },
  { key: 'hedefKum', name: 'Hedef payı', color: '#94a3b8', dash: '5 4' },
  { key: 'emsalKum', name: 'Emsal ortalaması', color: '#f59e0b', dash: '2 3' },
] as const;

function Stat({ label, value, help, k, alan }: { label: string; value: string; help: string; k?: Kaynaklar; alan?: string }) {
  return (
    <div className="rounded-2xl border border-slate-100 bg-white/80 p-3">
      <div className="flex items-start justify-between gap-1 text-[11px] font-bold uppercase tracking-wide text-canvas-muted">{label}{alan && <SqlInfo k={k} alan={alan} label={label} />}</div>
      <div className="mt-1 font-mono text-[20px] font-bold leading-none tabular-nums">{value}</div>
      <div className="mt-1 text-[11px] leading-snug text-canvas-muted">{help}</div>
    </div>
  );
}

/** Depo stokunun kaynağı ve tarihi; CRM sinyali seçildiyse Logo görünümünün son okuması da yazılır. */
function depotHelp(p: Depot | null | undefined): string {
  if (!p?.kaynakAdi) return 'Okunmadı';
  const base = `${p.kaynakAdi}${p.tarih ? ` · ${fmtDay(p.tarih)}` : ''}`;
  if (p.kaynak !== 'crm' || p.logo == null) return base;
  return `${base} · Logo depo görünümü ${fmtInt(p.logo)}${p.logoGun ? ` (${fmtDay(p.logoGun)})` : ''}`;
}

export default function TrackingTab({ launch, meta, gun, onGun }: { launch: Launch; meta: LaunchMeta; gun: 7 | 30; onGun: (g: 7 | 30) => void }) {
  const q = useQuery({ queryKey: ['launch', 'tracking', launch.id, gun], queryFn: () => launchApi.tracking(launch.id, gun), enabled: ENGINE_ENABLED });
  const d = q.data;
  const data = (d?.seri ?? []).filter((r) => r.d >= 0).map((r) => ({ ...r, x: dLabel(r.d) }));
  const logoEnd = d?.veriSonu.logo ?? null;
  const logoEndD = logoEnd ? Math.round((Date.parse(logoEnd) - Date.parse(launch.yayinGunu)) / 86_400_000) : null;
  const sig = d?.sinyal;

  return (
    <div className="flex flex-col gap-3">
      <Block
        title={`İlk ${gun} gün`}
        info={<SqlInfo k={d?.kaynaklar} alan="seri[]" label={`İlk ${gun} gün grafiği`} />}
        help={`Birikimli adet, yayın gününden itibaren. Sipariş CRM'den saatte bir okunur (sipariş satış değildir); faturalı satış Logo'dan günde bir${logoEnd ? `, veri ${fmtDay(logoEnd)} tarihinde bitiyor` : ''}. Hedef payı: yürürlükteki bütçe planının aylık hedefi ÷ ayın gün sayısı.`}
        action={
          <div className="flex rounded-xl bg-slate-100 p-1" role="radiogroup" aria-label="Dönem">
            {([7, 30] as const).map((g) => (
              <button key={g} type="button" role="radio" aria-checked={gun === g} onClick={() => onGun(g)}
                className={`min-h-11 rounded-lg px-3 text-[12.5px] font-extrabold transition-colors duration-150 sm:min-h-9 ${gun === g ? 'bg-white text-canvas-ink shadow-sm' : 'text-canvas-muted'}`}>
                İlk {g} gün
              </button>
            ))}
          </div>
        }
      >
        {q.error && <Note tone="err">{errText(q.error, 'İzleme açılamadı.')}</Note>}
        {q.isLoading && <Loading />}
        {d && (
          <>
            {logoEnd && logoEnd < new Date().toISOString().slice(0, 10) && (
              <Note tone="warn">Faturalı satış verisi {fmtDay(logoEnd)} tarihinde bitiyor; sonraki günler için yalnız CRM sipariş sinyali var. Bu bir «anlık satış» değildir.</Note>
            )}
            {d.okumaHatalari.length > 0 && <div className="mt-2"><Note tone="err">Son okumada okunamayan kaynak: {d.okumaHatalari.join(' · ')}</Note></div>}
            <div className="mt-3 h-[260px] w-full sm:h-[300px]">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={data} margin={{ top: 6, right: 8, left: 0, bottom: 0 }}>
                  <CartesianGrid vertical={false} stroke="#e2e8f0" />
                  <XAxis dataKey="x" tick={{ fontSize: 11 }} tickLine={false} axisLine={false} interval="preserveStartEnd" minTickGap={16} />
                  <YAxis tickFormatter={(v: number) => fmtInt(v)} tick={{ fontSize: 11 }} width={52} tickLine={false} axisLine={false} />
                  <Tooltip formatter={(v) => (typeof v === 'number' ? `${fmtInt(v)} adet` : '—')} />
                  <Legend wrapperStyle={{ fontSize: 12 }} />
                  {logoEndD !== null && logoEndD >= 0 && logoEndD < gun && (
                    <ReferenceLine x={dLabel(logoEndD)} stroke="#6d28d9" strokeDasharray="3 3" label={{ value: 'Logo veri sonu', fontSize: 10, fill: '#6d28d9', position: 'insideTopRight' }} />
                  )}
                  {SERIES.map((s) => (
                    <Line key={s.key} type="monotone" dataKey={s.key} name={s.name} stroke={s.color} strokeWidth={2}
                      strokeDasharray={'dash' in s ? s.dash : undefined} dot={false} connectNulls={false} isAnimationActive={false} />
                  ))}
                </LineChart>
              </ResponsiveContainer>
            </div>
            <div className="mt-3 grid grid-cols-2 gap-2 lg:grid-cols-4">
              <Stat label="Sipariş" value={fmtInt(d.toplam.siparis)} help={`CRM, ilk ${gun} gün (bugüne kadar)`} k={d.kaynaklar} alan="toplam" />
              <Stat label="Faturalı satış" value={fmtInt(d.toplam.fatura)}
                help={meta.me.canSeeBudget && d.toplam.ciro != null ? `${fmtMoney(d.toplam.ciro)} net ciro · Logo` : 'Logo, veri sonuna kadar'} k={d.kaynaklar} alan="toplam" />
              <Stat label="Hedef payı" value={fmtInt(d.toplam.hedef)}
                help={sig?.oran != null ? `${sig.oranEsas === 'fatura' ? 'Satış' : 'Sipariş'} / hedef: ${fmtPct(sig.oran)}` : 'Onaylı hedef yok ya da oran hesaplanamadı'} k={d.kaynaklar} alan="sinyal" />
              <Stat label="Emsal ortalaması" value={fmtInt(gun === 7 ? d.toplam.emsal7 : d.toplam.emsal30)}
                help={d.emsal.items.length ? `${d.emsal.items.length} emsal, ilk satış gününden` : (d.emsal.not ?? 'Emsal yok')} k={d.kaynaklar} alan="emsal" />
            </div>
          </>
        )}
      </Block>

      {d && (
        <Block title="Rafa ulaşma" help="Dağılım siparişi ve açık sipariş CRM'den; depo stoku Logo depo görünümünden, Logo verisi eskiyse CRM'deki en son siparişin anındaki stoktan (kaynağı yazılı).">
          {sig?.stokCatismasi && <Note tone="err">Açık sipariş depo stokunun üstünde: ek baskı ya da depo transferi satışla konuşulmalı.</Note>}
          {sig?.dagilimYok && <Note tone="err">Yayın günü geçti; dağılım siparişi görünmüyor.</Note>}
          <div className="mt-2 grid grid-cols-2 gap-2 lg:grid-cols-4">
            <Stat label="Dağılım" value={fmtInt(d.dagilim?.adet)} help={d.dagilim ? `${fmtInt(d.dagilim.bayi)} bayi · ${fmtInt(d.dagilim.siparis)} sipariş · ${fmtDay(d.dagilim.bas)}–${fmtDay(d.dagilim.bit)}` : 'Okunmadı'} k={d.kaynaklar} alan="dagilim" />
            <Stat label="Açık sipariş" value={fmtInt(sig?.bekleyen)} help="Kapanmamış sipariş satırları (Baskı Öneri tanımı)" k={d.kaynaklar} alan="sinyal" />
            <Stat label="Bekleyen ürün" value={fmtInt(sig?.bekleyenUrun ?? [...d.seri].reverse().find((r) => r.bekleyenUrun != null)?.bekleyenUrun)} help="CRM «Bekleyen Ürün» (stok yokken açılan)" k={d.kaynaklar} alan="seri[]" />
            <Stat label="Depo stoku" value={fmtInt(d.depo?.deger)} help={depotHelp(d.depo)} k={d.kaynaklar} alan="depo" />
          </div>
        </Block>
      )}

      {d && (
        <Block title="Gün gün" help={`Yayından ${d.seri.filter((r) => r.d < 0).length} gün öncesinden. Açık sipariş, bekleyen ürün ve depo o günün okumasıdır; geçmiş günlere geriye yazılmaz.`}>
          <TableWrap>
            <thead className="bg-slate-50">
              <tr>
                {['Gün', 'Tarih', 'Sipariş', 'Dağılım', 'Faturalı', ...(meta.me.canSeeBudget ? ['Net ciro'] : []), 'Hedef payı', 'Açık sipariş', 'Depo'].map((h) => (
                  <th key={h} className={th}>{h === 'Gün' || h === 'Tarih' ? h : <InfoLabel k={d.kaynaklar} alan="seri[]">{h}</InfoLabel>}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {d.seri.filter((r) => !r.gelecek).map((r) => (
                <tr key={r.gun} className={`border-t border-slate-100 ${r.d === 0 ? 'bg-canvas-violet/5' : ''}`}>
                  <td className={`${td} font-mono font-bold tabular-nums`}>{dLabel(r.d)}</td>
                  <td className={td}>{fmtDay(r.gun)}</td>
                  <td className={`${td} tabular-nums`}>{fmtInt(r.siparis)}</td>
                  <td className={`${td} tabular-nums`}>{fmtInt(r.dagilim)}</td>
                  <td className={`${td} tabular-nums`}>{r.fatura == null ? <span className="text-canvas-muted">veri yok</span> : fmtInt(r.fatura)}</td>
                  {meta.me.canSeeBudget && <td className={`${td} tabular-nums`}>{fmtMoney(r.ciro)}</td>}
                  <td className={`${td} tabular-nums`}>{fmtInt(r.hedef)}</td>
                  <td className={`${td} tabular-nums`}>{fmtInt(r.bekleyen)}</td>
                  <td className={`${td} tabular-nums`}>{fmtInt(r.depo)}</td>
                </tr>
              ))}
            </tbody>
          </TableWrap>
        </Block>
      )}
    </div>
  );
}
