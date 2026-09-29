import { Link } from 'react-router-dom';
import { AlertTriangle, ChevronRight } from 'lucide-react';
import { Pill } from '../../admin/ui';
import { EmptyHint } from '../../components/Explain';
import { fmtShortDay } from '../api';
import { FOY_TONE, type Foy } from './api';

/** Ayın föyleri: masaüstünde tablo, telefonda kart listesi. Eksik alan ve uyumsuzluk satırda görünür. */

const nameOf = (f: Foy) => (f.alanlar.find((a) => a.key === 'ad')?.deger as string | null) ?? f.stokKodu;

function Flags({ f, fields }: { f: Foy; fields: Record<string, string> }) {
  return (
    <div className="flex flex-wrap gap-1">
      <Pill tone={FOY_TONE[f.durum]}>{f.durumAdi}</Pill>
      {f.eski && <Pill tone="err">CRM değişti</Pill>}
      {f.ayDisi && <Pill tone="muted">Yayın günü başka aya kaydı</Pill>}
      {f.eksikler.length > 0 && <Pill tone="warn">Eksik: {f.eksikler.map((k) => fields[k] ?? k).join(', ')}</Pill>}
      {f.engelleyen > 0 && (
        <span className="inline-flex items-center gap-1 rounded-md bg-red-50 px-1.5 py-0.5 text-[11px] font-bold text-red-700">
          <AlertTriangle aria-hidden className="h-3 w-3" />
          {f.uyumsuzluk.filter((m) => !m.bilgi).map((m) => m.ad).join(' · ')}
        </span>
      )}
    </div>
  );
}

export default function FoyTable({ rows, fields }: { rows: Foy[]; fields: Record<string, string> }) {
  if (rows.length === 0) return <EmptyHint title="Gösterilecek föy yok" why="Bu ay CRM'de yayın günü olan yeni kitap yok ya da seçtiğiniz durum süzgecine uyan föy yok. Başka bir ay seçin ya da durumu «Hepsi» yapın." />;
  const link = (f: Foy) => `/pazarlama/foy/${encodeURIComponent(f.stokKodu)}?ay=${f.donem}`;
  return (
    <>
      <div className="hidden overflow-x-auto rounded-2xl border border-slate-100 bg-white/80 md:block">
        <table className="w-full min-w-[760px] text-[12px]">
          <thead>
            <tr className="text-left text-[11px] font-bold uppercase tracking-wide text-canvas-muted">
              <th className="px-3 py-2">Kitap</th>
              <th className="px-3 py-2">Yayın</th>
              <th className="px-3 py-2">Durum</th>
              <th className="px-3 py-2">Sürüm</th>
              <th className="w-8 px-3 py-2" />
            </tr>
          </thead>
          <tbody>
            {rows.map((f) => (
              <tr key={f.id} className="border-t border-slate-100 align-top">
                <td className="px-3 py-2">
                  <Link to={link(f)} className="font-extrabold text-canvas-ink hover:underline">{nameOf(f)}</Link>
                  <div className="text-[11px] text-canvas-muted">{f.stokKodu}{f.kitap?.yazar ? ` · ${f.kitap.yazar}` : ''}{f.kitap?.kitaplik ? ` · ${f.kitap.kitaplik}` : ''}</div>
                </td>
                <td className="px-3 py-2 font-mono tabular-nums">{fmtShortDay(f.kitap?.yayinTarihi ?? null)}</td>
                <td className="px-3 py-2"><Flags f={f} fields={fields} /></td>
                <td className="px-3 py-2 font-mono tabular-nums">{f.surum}</td>
                <td className="px-3 py-2"><Link to={link(f)} aria-label={`${nameOf(f)} föyünü aç`}><ChevronRight className="h-4 w-4 text-canvas-muted" /></Link></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <ul className="flex flex-col gap-2 md:hidden">
        {rows.map((f) => (
          <li key={f.id}>
            <Link to={link(f)} className="flex min-h-11 flex-col gap-1 rounded-2xl bg-white/80 p-3 transition-transform duration-150 ease-out active:scale-[0.98]">
              <span className="text-[13px] font-extrabold leading-snug">{nameOf(f)}</span>
              <span className="text-[11px] text-canvas-muted">{f.stokKodu} · yayın {fmtShortDay(f.kitap?.yayinTarihi ?? null)}</span>
              <Flags f={f} fields={fields} />
            </Link>
          </li>
        ))}
      </ul>
    </>
  );
}
