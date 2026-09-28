import type { ReactNode } from 'react';
import { TableWrap, label as labelCls, td, th } from '../admin/ui';
import { fmtDay } from '../budget/api';
import { gunText, n0, n1, tl, type Item } from './api';
import { BookCell, StatePill, num } from './parts';

/** Kitap listesi: telefonda kart, tablet ve masaüstünde tablo. Kolonlar ekrana göre seçilir; geniş tablo kendi
 *  kapsayıcısında kayar (sayfa taşmaz). */

export type Col = 'bakiye' | 'crmRaf' | 'hiz' | 'gun' | 'tukenme' | 'bekleyen' | 'durum' | 'uretim' | 'fark' | 'aktarim'
  | 'devir' | 'sonHareket' | 'net12' | 'deger' | 'kritik';

const SPEC: Record<Col, { head: string; right?: boolean; cell: (i: Item) => ReactNode }> = {
  bakiye: { head: 'Logo stok', right: true, cell: (i) => n0(i.bakiye) },
  crmRaf: { head: 'CRM raf', right: true, cell: (i) => n0(i.crmRaf) },
  hiz: { head: 'Aylık satış hızı', right: true, cell: (i) => n1(i.satisHizi) },
  gun: { head: 'Kaç gün yeter', right: true, cell: (i) => gunText(i.gun) },
  tukenme: { head: 'Tahmini tükenme', cell: (i) => (i.tukenmeTarihi ? fmtDay(i.tukenmeTarihi) : '—') },
  bekleyen: {
    head: 'Bekleyen sipariş',
    right: true,
    cell: (i) => (
      <>
        {n0(i.bekleyenCrm)}
        {i.bekleyenLogo ? <div className="text-[11px] text-canvas-muted">Logo {n0(i.bekleyenLogo)}</div> : null}
      </>
    ),
  },
  durum: { head: 'Durum', cell: (i) => <StatePill state={i.durum} label={i.durumEtiket} /> },
  kritik: {
    head: 'Baskı + güvenlik',
    right: true,
    cell: (i) => (
      <>
        {n0(i.kritikGun)} gün
        {i.baskiUyarisi ? <div className="text-[11px] font-bold text-amber-700">altında</div> : null}
      </>
    ),
  },
  uretim: {
    head: 'Açık üretim',
    cell: (i) =>
      i.uretim ? (
        <>
          <div className="font-semibold">{i.uretim.asamaEtiket}</div>
          <div className="text-[11px] text-canvas-muted">
            {i.uretim.adet ? `${n0(i.uretim.adet)} adet · ` : ''}depo {i.uretim.depoPlan ? fmtDay(i.uretim.depoPlan) : 'planı yok'}
          </div>
        </>
      ) : (
        <span className="text-[11.5px] font-semibold text-canvas-muted">Kart yok</span>
      ),
  },
  fark: {
    head: 'Fark (CRM − Logo)',
    right: true,
    cell: (i) => <span className={i.fark && i.fark < 0 ? 'text-red-700' : ''}>{i.fark !== null && i.fark > 0 ? '+' : ''}{n0(i.fark)}</span>,
  },
  aktarim: {
    head: 'Kök neden',
    cell: (i) => (
      <>
        <div className="font-semibold">{i.farkEtiket ?? '—'}</div>
        {i.aktarimBekleyen ? <div className="text-[11px] text-canvas-muted">aktarılmamış {n0(i.aktarimBekleyen)} ({i.aktarimFis} fiş)</div> : null}
      </>
    ),
  },
  devir: { head: 'Devir hızı', right: true, cell: (i) => (i.devirHizi === null ? '—' : n1(i.devirHizi)) },
  sonHareket: { head: 'Son hareket', cell: (i) => (i.sonHareket ? fmtDay(i.sonHareket) : 'pencerede yok') },
  net12: { head: '12 ay net satış', right: true, cell: (i) => n0(i.netSatis12) },
  deger: { head: 'Stok değeri', right: true, cell: (i) => (i.stokDegeri === undefined ? '—' : i.stokDegeri === null ? 'maliyet yok' : tl(i.stokDegeri)) },
};

export default function ItemList({ items, cols, action }: { items: Item[]; cols: Col[]; action?: (i: Item) => ReactNode }) {
  const shown = cols.filter((c) => c !== 'deger' || items.some((i) => i.stokDegeri !== undefined));
  return (
    <>
      <ul className="flex flex-col gap-2 md:hidden">
        {items.map((i) => (
          <li key={i.stokKodu} className="rounded-2xl border border-slate-100 bg-white/80 p-3">
            <div className="flex items-start justify-between gap-2">
              <BookCell it={i} />
              {shown.includes('durum') && <StatePill state={i.durum} label={i.durumEtiket} />}
            </div>
            <dl className="mt-2 grid grid-cols-2 gap-x-3 gap-y-2 text-[11.5px]">
              {shown
                .filter((c) => c !== 'durum')
                .map((c) => (
                  <div key={c} className="min-w-0">
                    <dt className={labelCls}>{SPEC[c].head}</dt>
                    <dd className={SPEC[c].right ? 'font-mono tabular-nums' : ''}>{SPEC[c].cell(i)}</dd>
                  </div>
                ))}
            </dl>
            {action && <div className="mt-2 flex flex-wrap justify-end gap-2">{action(i)}</div>}
          </li>
        ))}
      </ul>
      <div className="hidden md:block">
        <TableWrap>
          <thead>
            <tr>
              <th className={th}>Kitap</th>
              {shown.map((c) => (
                <th key={c} className={`${th} ${SPEC[c].right ? 'text-right' : ''}`}>{SPEC[c].head}</th>
              ))}
              {action && <th className={th} />}
            </tr>
          </thead>
          <tbody>
            {items.map((i) => (
              <tr key={i.stokKodu} className="border-t border-slate-100">
                <td className={td}>
                  <BookCell it={i} />
                </td>
                {shown.map((c) => (
                  <td key={c} className={`${td} ${SPEC[c].right ? num : ''}`}>{SPEC[c].cell(i)}</td>
                ))}
                {action && <td className={`${td} text-right`}>{action(i)}</td>}
              </tr>
            ))}
          </tbody>
        </TableWrap>
      </div>
    </>
  );
}
