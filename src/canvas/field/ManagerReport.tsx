import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { ChevronLeft, ChevronRight, Download } from 'lucide-react';
import { ENGINE_ENABLED } from '../engine';
import { Loading, Note, TableWrap, btnGhost, errText, label as labelCls, td, th } from '../admin/ui';
import { fieldApi, fmtDay, fmtMoney, fmtPct, type FieldMeta, type RepRow } from './api';
import { Empty } from './parts';

/** Haftalık saha raporu: temsilci × hedef–gerçekleşme, vadesi geçmiş, tahsilat, ziyaret. Temsilci karşılaştırması kişisel
 *  performans verisidir: yalnız `saha.performans` yetkilisi bütün satırları görür, öteki kişi kendi satırını. Telefonda kart,
 *  masaüstünde tablo (kendi kabında kayar). */

/** Haftanın pazartesisi (YYYY-AA-GG). Hafta ileri/geri düğmesiyle seçilir: telefon tarayıcılarının bir kısmında hafta
 *  seçici yok. */
export function mondayOf(d: Date): string {
  const t = new Date(Date.UTC(d.getFullYear(), d.getMonth(), d.getDate()));
  t.setUTCDate(t.getUTCDate() - ((t.getUTCDay() + 6) % 7));
  return t.toISOString().slice(0, 10);
}

export function shiftDays(day: string, n: number): string {
  const t = new Date(`${day}T00:00:00Z`);
  t.setUTCDate(t.getUTCDate() + n);
  return t.toISOString().slice(0, 10);
}

export default function ManagerReport({ meta, temsilci }: { meta: FieldMeta; temsilci: string }) {
  const thisWeek = mondayOf(new Date());
  const [week, setWeek] = useState(() => shiftDays(thisWeek, -7));
  const q = useQuery({ queryKey: ['field', 'weekly', week, temsilci], queryFn: () => fieldApi.weekly({ hafta: week, temsilci }), enabled: ENGINE_ENABLED });
  const d = q.data;
  const err = errText(q.error, 'Haftalık rapor okunamadı.');

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-end justify-between gap-2">
        <div className="flex w-full flex-col gap-1 sm:w-auto">
          <span className={labelCls}>Hafta</span>
          <div className="flex items-center gap-1.5">
            <button type="button" aria-label="Önceki hafta" className={`${btnGhost} !w-11 !px-0`} onClick={() => setWeek((w) => shiftDays(w, -7))}>
              <ChevronLeft aria-hidden className="h-4 w-4" />
            </button>
            <span className="min-w-0 flex-1 text-center font-mono text-[12.5px] font-bold tabular-nums sm:w-44 sm:flex-none">
              {fmtDay(week)} – {fmtDay(shiftDays(week, 6))}
            </span>
            <button
              type="button"
              aria-label="Sonraki hafta"
              className={`${btnGhost} !w-11 !px-0`}
              disabled={week >= thisWeek}
              onClick={() => setWeek((w) => shiftDays(w, 7))}
            >
              <ChevronRight aria-hidden className="h-4 w-4" />
            </button>
          </div>
        </div>
        {meta.me.canExport && d && (
          <a className={btnGhost} href={fieldApi.weeklyXlsxUrl({ hafta: week, temsilci })} download>
            <Download aria-hidden className="h-4 w-4" />
            Excel
          </a>
        )}
      </div>
      {!meta.me.canPerformance && (
        <Note tone="info">Temsilci karşılaştırması yetkiyle açılır; burada yalnız kendi satırınız görünür.</Note>
      )}
      {err && <Note tone="err">{err}</Note>}
      {d?.warning && <Note tone="warn">{d.warning}</Note>}
      {q.isLoading ? (
        <Loading />
      ) : !d ? null : d.items.length === 0 ? (
        <Empty>Bu hafta için rapor satırı yok.</Empty>
      ) : (
        <>
          <p className="px-1 text-[11.5px] text-canvas-muted">
            {fmtDay(d.start)} – {fmtDay(d.end)} · satış ve alacak {fmtDay(d.asof)} sabahki veriden (Logo {fmtDay(d.dataEnd)} tarihine kadar). Vadesi geçmiş tutarlar yaklaşıktır (FIFO).
          </p>
          <ul className="flex flex-col gap-2 lg:hidden">
            {d.items.map((r) => (
              <RepCard key={r.hesap ?? 'yok'} r={r} />
            ))}
          </ul>
          <div className="hidden lg:block">
            <TableWrap>
              <thead>
                <tr>
                  {['Temsilci', 'Cari', 'Yıl başından', 'Geçen yıl', 'Hedef oranı', 'Vadesi geçmiş', '90+ gün', 'Onay bekleyen', 'Reddedilen', 'Ziyaret', 'Notlu'].map((h) => (
                    <th key={h} className={th}>
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {d.items.map((r) => (
                  <tr key={r.hesap ?? 'yok'} className="border-t border-slate-100">
                    <td className={`${td} font-bold`}>{r.ad}</td>
                    <td className={`${td} font-mono tabular-nums`}>{r.cari}</td>
                    <td className={`${td} font-mono tabular-nums`}>{fmtMoney(r.ytd)}</td>
                    <td className={`${td} font-mono tabular-nums`}>
                      {fmtMoney(r.gecenYil)} <span className="text-canvas-muted">{r.buyume !== null ? `(${r.buyume >= 0 ? '+' : ''}${fmtPct(r.buyume)})` : ''}</span>
                    </td>
                    <td className={`${td} font-mono tabular-nums ${r.hedefOrani !== null && r.hedefOrani < 0.8 ? 'text-red-700' : ''}`}>{fmtPct(r.hedefOrani)}</td>
                    <td className={`${td} font-mono tabular-nums`}>{fmtMoney(r.vadesiGecmis)}</td>
                    <td className={`${td} font-mono tabular-nums ${r.k90 > 0 ? 'text-red-700' : ''}`}>{fmtMoney(r.k90)}</td>
                    <td className={`${td} font-mono tabular-nums`}>
                      {r.onayBekleyen} <span className="text-canvas-muted">({fmtMoney(r.onayBekleyenTutar)})</span>
                    </td>
                    <td className={`${td} font-mono tabular-nums`}>{r.reddedilen}</td>
                    <td className={`${td} font-mono tabular-nums`}>{r.ziyaret}</td>
                    <td className={`${td} font-mono tabular-nums`}>{r.not}</td>
                  </tr>
                ))}
              </tbody>
            </TableWrap>
          </div>
        </>
      )}
    </div>
  );
}

function RepCard({ r }: { r: RepRow }) {
  const cells: Array<[string, string, boolean?]> = [
    ['Yıl başından', fmtMoney(r.ytd)],
    ['Hedef oranı', fmtPct(r.hedefOrani), r.hedefOrani !== null && r.hedefOrani < 0.8],
    ['Vadesi geçmiş', fmtMoney(r.vadesiGecmis)],
    ['90+ gün', fmtMoney(r.k90), r.k90 > 0],
    ['Onay bekleyen', `${r.onayBekleyen}`],
    ['Reddedilen', `${r.reddedilen}`],
    ['Ziyaret', `${r.ziyaret} (${r.not} notlu)`],
    ['Geçen yıla göre', r.buyume === null ? '—' : `${r.buyume >= 0 ? '+' : ''}${fmtPct(r.buyume)}`],
  ];
  return (
    <li className="rounded-2xl border border-slate-100 bg-white/85 p-3">
      <div className="flex items-baseline justify-between gap-2">
        <div className="min-w-0 truncate text-[13.5px] font-extrabold">{r.ad}</div>
        <div className="shrink-0 text-[11.5px] text-canvas-muted">{r.cari} cari</div>
      </div>
      <dl className="mt-2 grid grid-cols-2 gap-x-3 gap-y-1">
        {cells.map(([k, v, bad]) => (
          <div key={k} className="flex min-w-0 items-baseline justify-between gap-2 border-b border-slate-100 py-1">
            <dt className="min-w-0 truncate text-[11.5px] text-canvas-muted">{k}</dt>
            <dd className={`shrink-0 font-mono text-[12px] font-bold tabular-nums ${bad ? 'text-red-700' : ''}`}>{v}</dd>
          </div>
        ))}
      </dl>
    </li>
  );
}
