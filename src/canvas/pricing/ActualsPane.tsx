import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useSearchParams } from 'react-router-dom';
import { Search } from 'lucide-react';
import { ENGINE_ENABLED } from '../engine';
import { Loading, Note, TableWrap, btnGhost, errText, field, td, th } from '../admin/ui';
import { useDebounced } from '../editorial/kit';
import { day, mn, num, pct, pricingApi, tl0, tl2 } from './api';
import { Select, Stat } from './parts';
import SqlInfo, { InfoLabel } from '../components/SqlInfo';

const PAGE = 100;
const YEARS = ['', '2021', '2022', '2023', '2024', '2025', '2026'];

/** Gerçekleşen maliyet ve marj (Logo): kitap başına basılan, baskı bedeli, satılan, net satış, Logo birim maliyeti, brüt kâr. */
export default function ActualsPane({ ready }: { ready: boolean }) {
  const [, setParams] = useSearchParams();
  const [q, setQ] = useState('');
  const [since, setSince] = useState('');
  const [sort, setSort] = useState<'net' | 'margin' | 'printed' | 'costToPrice'>('net');
  const [pages, setPages] = useState(1);
  const dq = useDebounced(q.trim(), 300);
  const data = useQuery({
    queryKey: ['pricing', 'actuals', dq, since, sort, pages],
    queryFn: () => pricingApi.actuals({ q: dq, since: since ? Number(since) : null, sort, offset: 0, limit: PAGE * pages }),
    enabled: ENGINE_ENABLED && ready,
    placeholderData: (p) => p,
  });
  const d = data.data;
  if (!ready) return <Note tone="info">Logo verisi hazırlanınca gerçekleşen maliyet ve marj burada görünür.</Note>;

  return (
    <div className="flex flex-col gap-3">
      <div className="grid grid-cols-1 gap-2 sm:grid-cols-[1fr_auto_auto]">
        <label className="relative block">
          <span className="sr-only">Kitap ara</span>
          <Search aria-hidden className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-canvas-muted" />
          <input className={`${field} pl-9`} value={q} placeholder="Kitap adı ya da stok kodu" onChange={(e) => (setQ(e.target.value), setPages(1))} />
        </label>
        <Select<string>
          label="Dönem"
          value={since}
          onChange={(v) => (setSince(v), setPages(1))}
          options={YEARS.map((y) => ({ value: y, label: y ? `${y}'den bu yana` : "2021'den bu yana (tümü)" }))}
        />
        <Select<'net' | 'margin' | 'printed' | 'costToPrice'>
          label="Sıra"
          value={sort}
          onChange={(v) => (setSort(v), setPages(1))}
          options={[
            { value: 'net', label: 'Net satış (büyükten)' },
            { value: 'margin', label: 'Brüt marj (düşükten)' },
            { value: 'printed', label: 'Basılan adet' },
            { value: 'costToPrice', label: 'Maliyetin fiyata oranı' },
          ]}
        />
      </div>
      {data.error && <Note tone="err">{errText(data.error, 'Veri okunamadı.')}</Note>}
      {!d ? (
        !data.error && <Loading />
      ) : (
        <>
          <div className="grid grid-cols-2 gap-2 lg:grid-cols-5">
            <Stat info={<SqlInfo k={d.kaynaklar} alan="count" label="Kitap" />} label="Kitap" value={num(d.count)} note={`Veri sonu ${day(d.dataEnd)}`} />
            <Stat info={<SqlInfo k={d.kaynaklar} alan="net" label="Net satış" />} label="Net satış" value={mn(d.net)} note={`${num(d.sold)} adet (faturalı, iade düşülmüş)`} />
            <Stat info={<SqlInfo k={d.kaynaklar} alan="printCost" label="Baskı faturaları" />} label="Baskı faturaları" value={mn(d.printCost)} note={`${num(d.printed)} adet basıldı (kâğıt hariç)`} />
            <Stat info={<SqlInfo k={d.kaynaklar} alan="margin" label="Brüt marj" />} label="Brüt marj" value={pct(d.margin)} note="Net satış − Logo satılan malın maliyeti; maliyetli satırlar" />
            <Stat info={<SqlInfo k={d.kaynaklar} alan="gosterilen" label="Gösterilen kitap sayısı" />} label="Gösterilen" value={num(d.rows.length)} note={d.rows.length < d.count ? 'Aşağıdan fazlasını açın' : 'Hepsi'} />
          </div>
          <TableWrap>
            <thead>
              <tr>
                <th className={th}>Kitap</th>
                <th className={`${th} text-right`}><InfoLabel k={d.kaynaklar} alan="rows[].printed">Basılan</InfoLabel></th>
                <th className={`${th} text-right`}><InfoLabel k={d.kaynaklar} alan="rows[].printUnit">Baskı / adet</InfoLabel></th>
                <th className={`${th} text-right`}><InfoLabel k={d.kaynaklar} alan="rows[].sold">Satılan</InfoLabel></th>
                <th className={`${th} text-right`}><InfoLabel k={d.kaynaklar} alan="rows[].net">Net satış</InfoLabel></th>
                <th className={`${th} text-right`}><InfoLabel k={d.kaynaklar} alan="rows[].avgNet">Ort. net fiyat</InfoLabel></th>
                <th className={`${th} text-right`}><InfoLabel k={d.kaynaklar} alan="rows[].unitCost">Logo birim maliyet</InfoLabel></th>
                <th className={`${th} text-right`}><InfoLabel k={d.kaynaklar} alan="rows[].profit">Brüt kâr</InfoLabel></th>
                <th className={`${th} text-right`}><InfoLabel k={d.kaynaklar} alan="rows[].margin">Marj</InfoLabel></th>
                <th className={`${th} text-right`}><InfoLabel k={d.kaynaklar} alan="rows[].price">Kapak fiyatı</InfoLabel></th>
                <th className={`${th} text-right`}><InfoLabel k={d.kaynaklar} alan="rows[].costToPrice">Maliyet / fiyat</InfoLabel></th>
              </tr>
            </thead>
            <tbody>
              {d.rows.map((r) => (
                <tr key={r.code} className="cursor-pointer border-t border-slate-100 hover:bg-slate-50" onClick={() => setParams({ bolum: 'hesap', kitap: r.code })}>
                  <td className={td}>
                    <div className="font-bold">{r.name}</div>
                    <div className="text-[11px] text-canvas-muted">
                      {[r.code, r.publisher, r.lastPrintDate ? `son baskı ${day(r.lastPrintDate)}` : null].filter(Boolean).join(' · ')}
                    </div>
                  </td>
                  <td className={`${td} text-right tabular-nums`}>{num(r.printed)}</td>
                  <td className={`${td} text-right tabular-nums`}>{tl2(r.printUnit)}</td>
                  <td className={`${td} text-right tabular-nums`}>{num(r.sold)}</td>
                  <td className={`${td} text-right tabular-nums`}>{tl0(r.net)}</td>
                  <td className={`${td} text-right tabular-nums`}>{tl2(r.avgNet)}</td>
                  <td className={`${td} text-right tabular-nums`} title={r.costCoverage != null ? `Satışların ${pct(r.costCoverage)}'i maliyetli` : undefined}>
                    {tl2(r.unitCost)}
                  </td>
                  <td className={`${td} text-right tabular-nums ${r.profit != null && r.profit < 0 ? 'text-red-600' : ''}`}>{tl0(r.profit)}</td>
                  <td className={`${td} text-right tabular-nums`}>{pct(r.margin)}</td>
                  <td className={`${td} text-right tabular-nums`}>{tl0(r.price)}</td>
                  <td className={`${td} text-right tabular-nums`}>{pct(r.costToPrice)}</td>
                </tr>
              ))}
            </tbody>
          </TableWrap>
          {d.rows.length < d.count && (
            <div className="flex justify-center">
              <button type="button" className={btnGhost} disabled={data.isFetching} onClick={() => setPages((p) => p + 1)}>
                {data.isFetching ? 'Yükleniyor…' : `Sonraki ${num(Math.min(PAGE, d.count - d.rows.length))} kitap`}
              </button>
            </div>
          )}
          <p className="px-1 text-[11px] leading-snug text-canvas-muted">
            Basılan ve baskı bedeli matbaanın «komple baskı» faturalarından (kâğıt Timaş'ın, faturada yok). Satış yalnız faturalı satırlar; iade düşülür. Logo birim maliyeti
            satış satırındaki maliyet (kâğıt + baskı + üretime yüklenen); maliyeti olmayan satırlar marja girmez, oranı imleçle görünür. Telif ve genel gider brüt kâra
            dahil değildir. Maliyet / fiyat = Logo birim maliyeti ÷ KDV hariç güncel kapak fiyatı.
          </p>
        </>
      )}
    </div>
  );
}
