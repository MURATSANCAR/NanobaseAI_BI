import { Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { ENGINE_ENABLED } from '../engine';
import { Note, Pill, TableWrap, errText, td, th } from '../admin/ui';
import { Panel } from '../editorial/kit';
import { fmtDay, fmtMoney, fmtPct, tendersApi } from './api';
import SqlInfo, { InfoLabel } from '../components/SqlInfo';

/** Sonuçlanan ihaleler: kazanılan/kaybedilen, kazanan firma ve fiyat, kayıp nedeni; kurum türüne göre kazanma oranı ve
 *  kazanan fiyatın liste fiyatına oranı (teklif fiyatı önerisinin dayanağı). */
export default function ResultsTab() {
  const res = useQuery({ queryKey: ['tenders', 'results'], queryFn: tendersApi.results, enabled: ENGINE_ENABLED });
  const items = res.data?.items ?? [];
  return (
    <>
      <Panel>
        <h2 className="flex items-center gap-1 text-[16px] font-extrabold tracking-tight">Kurum türüne göre<SqlInfo k={res.data?.kaynaklar} alan="ozet[]" label="Kurum türüne göre sonuçlar" /></h2>
        <p className="text-[12px] text-canvas-muted">«Kazanan / liste» = kazanan teklifin aynı kalemlerin KDV hariç liste toplamına oranı (ortanca). Yeni ihalede fiyat oranı önerisi buradan gelir.</p>
        {res.error && <div className="mt-2"><Note tone="err">{errText(res.error, 'Sonuçlar okunamadı.')}</Note></div>}
        <div className="mt-3 grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-4">
          {(res.data?.ozet ?? []).map((o) => (
            <div key={o.kurumTuru} className="rounded-xl bg-white/80 px-3 py-2">
              <div className="text-[11px] font-bold uppercase tracking-wide text-canvas-muted">{o.kurumTuruAdi}</div>
              <div className="mt-0.5 font-mono text-[18px] font-bold tabular-nums">{o.kazanilan}/{o.sonuc}</div>
              <div className="text-[11.5px] text-canvas-muted">kazanılan · kazanan/liste {fmtPct(o.kazananOranOrtanca)} ({o.oranSayisi} fiyatlı sonuç)</div>
            </div>
          ))}
          {res.data && !res.data.ozet.length && <div className="text-[12.5px] text-canvas-muted">Henüz sonuç kaydı yok.</div>}
        </div>
      </Panel>
      {items.length > 0 && (
        <TableWrap>
          <thead>
            <tr className="border-b border-slate-100">
              <th className={th}>Kurum</th>
              <th className={th}>Sonuç</th>
              <th className={th}>Kazanan</th>
              <th className={`${th} text-right`}><InfoLabel k={res.data?.kaynaklar} alan="items[]" label="Kazanan fiyat">Kazanan fiyat</InfoLabel></th>
              <th className={`${th} text-right`}><InfoLabel k={res.data?.kaynaklar} alan="items[]" label="Bizim teklif">Bizim teklif</InfoLabel></th>
              <th className={`${th} text-right`}><InfoLabel k={res.data?.kaynaklar} alan="items[]" label="Kazanan / liste">Kazanan / liste</InfoLabel></th>
              <th className={th}>Neden</th>
              <th className={th}>Tarih</th>
            </tr>
          </thead>
          <tbody>
            {items.map((r) => (
              <tr key={r.id} className="border-b border-slate-50 last:border-0">
                <td className={td}>
                  <Link to={`/ihale/${r.id}`} className="font-bold text-canvas-violet hover:underline">{r.kurum}</Link>
                  <div className="text-[11px] text-canvas-muted">{r.kurumTuruAdi}{r.il ? ` · ${r.il}` : ''}</div>
                </td>
                <td className={td}><Pill tone={r.sonuc === 'kazanildi' ? 'ok' : r.sonuc === 'kaybedildi' ? 'err' : 'muted'}>{r.sonucAdi}</Pill></td>
                <td className={td}>{r.kazanan ?? '—'}</td>
                <td className={`${td} text-right font-mono tabular-nums`}>{fmtMoney(r.kazananFiyat)}</td>
                <td className={`${td} text-right font-mono tabular-nums`}>{fmtMoney(r.bizimFiyat)}</td>
                <td className={`${td} text-right font-mono tabular-nums`}>{fmtPct(r.kazananListeOrani)}</td>
                <td className={`${td} max-w-[280px] break-words`}>{r.neden ?? '—'}</td>
                <td className={`${td} whitespace-nowrap`}>{fmtDay(r.zaman)}</td>
              </tr>
            ))}
          </tbody>
        </TableWrap>
      )}
    </>
  );
}
