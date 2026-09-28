import type { ReactNode } from 'react';
import { TableWrap, label as labelCls, td, th } from '../admin/ui';
import { fmtDay } from '../budget/api';
import { InfoLabel } from '../components/SqlInfo';
import type { Kaynaklar } from '../components/sqlInfo';
import { gunText, n0, n1, tl, type Item } from './api';
import { BookCell, StatePill, num } from './parts';

/** Kitap listesi: telefonda kart, tablet ve masaüstünde tablo. Kolonlar ekrana göre seçilir; geniş tablo kendi
 *  kapsayıcısında kayar (sayfa taşmaz). */

export type Col = 'bakiye' | 'crmRaf' | 'hiz' | 'gun' | 'tukenme' | 'bekleyen' | 'durum' | 'uretim' | 'fark' | 'aktarim'
  | 'devir' | 'sonHareket' | 'net12' | 'deger' | 'kritik' | 'tahmin90';

/** `alan`: kolonun sorgu bilgisindeki alan adı (satır yolunun altında, ör. «items[].bakiye»); yoksa kolon rakam değil. */
const SPEC: Record<Col, { head: string; alan?: string; right?: boolean; cell: (i: Item) => ReactNode }> = {
  bakiye: { head: 'Logo stok', alan: 'bakiye', right: true, cell: (i) => n0(i.bakiye) },
  crmRaf: { head: 'CRM raf', alan: 'crmRaf', right: true, cell: (i) => n0(i.crmRaf) },
  hiz: { head: 'Aylık satış hızı', alan: 'satisHizi', right: true, cell: (i) => n1(i.satisHizi) },
  gun: { head: 'Kaç gün yeter', alan: 'gun', right: true, cell: (i) => gunText(i.gun) },
  tukenme: { head: 'Tahmini tükenme', alan: 'gun', cell: (i) => (i.tukenmeTarihi ? fmtDay(i.tukenmeTarihi) : '—') },
  bekleyen: {
    head: 'Bekleyen sipariş',
    alan: 'bekleyenCrm',
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
    alan: 'kritikGun',
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
    alan: 'uretim',
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
    alan: 'fark',
    right: true,
    cell: (i) => <span className={i.fark && i.fark < 0 ? 'text-red-700' : ''}>{i.fark !== null && i.fark > 0 ? '+' : ''}{n0(i.fark)}</span>,
  },
  aktarim: {
    head: 'Kök neden',
    alan: 'aktarimBekleyen',
    cell: (i) => (
      <>
        <div className="font-semibold">{i.farkEtiket ?? '—'}</div>
        {i.aktarimBekleyen ? <div className="text-[11px] text-canvas-muted">aktarılmamış {n0(i.aktarimBekleyen)} ({i.aktarimFis} fiş)</div> : null}
      </>
    ),
  },
  devir: { head: 'Devir hızı', alan: 'devirHizi', right: true, cell: (i) => (i.devirHizi === null ? '—' : n1(i.devirHizi)) },
  sonHareket: { head: 'Son hareket', alan: 'netSatis12', cell: (i) => (i.sonHareket ? fmtDay(i.sonHareket) : 'pencerede yok') },
  net12: { head: '12 ay net satış', alan: 'netSatis12', right: true, cell: (i) => n0(i.netSatis12) },
  tahmin90: {
    head: 'Tahmin · 90 gün',
    alan: 'tahminAralik',
    right: true,
    cell: (i) => {
      const b = i.tahminAralik?.g90;
      if (!b || b.p50 === null) return <span className="text-canvas-muted">—</span>;
      return (
        <>
          {n0(b.p50)}
          {b.aralik ? <div className="text-[11px] text-canvas-muted">{n0(b.p10)}–{n0(b.p90)}</div> : null}
        </>
      );
    },
  },
  deger: { head: 'Stok değeri', alan: 'stokDegeri', right: true, cell: (i) => (i.stokDegeri === undefined ? '—' : i.stokDegeri === null ? 'maliyet yok' : tl(i.stokDegeri)) },
};

/**
 * `k` + `base`: sorgu bilgisi (cevabın `kaynaklar`ı ve satırların yolu, ör. «items[]», «bugun.bitecek.items[]»). Tabloda
 * her kolon başlığında «i»; telefonda kartların üstünde bir kez kolon başına «i» (her kartta tekrar etmez).
 */
export default function ItemList({ items, cols, action, k, base = 'items[]' }: {
  items: Item[];
  cols: Col[];
  action?: (i: Item) => ReactNode;
  k?: Kaynaklar | null;
  base?: string;
}) {
  const shown = cols.filter((c) => (c !== 'deger' || items.some((i) => i.stokDegeri !== undefined))
    && (c !== 'tahmin90' || items.some((i) => i.tahminAralik?.g90)));
  const head = (c: Col) => {
    const a = SPEC[c].alan;
    return a && k ? <InfoLabel k={k} alan={`${base}.${a}`}>{SPEC[c].head}</InfoLabel> : SPEC[c].head;
  };
  const infoCols = k ? shown.filter((c) => SPEC[c].alan) : [];
  return (
    <>
      {infoCols.length > 0 && (
        <div className="mb-2 flex flex-wrap gap-x-3 gap-y-1 text-[11px] font-semibold text-canvas-muted md:hidden" aria-label="Kolonların sorgu bilgisi">
          {infoCols.map((c) => (
            <span key={c}>{head(c)}</span>
          ))}
        </div>
      )}
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
                <th key={c} className={`${th} ${SPEC[c].right ? 'text-right' : ''}`}>{head(c)}</th>
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
