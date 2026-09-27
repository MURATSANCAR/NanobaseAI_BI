import { useState } from 'react';
import { Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { Note, TableWrap, errText, label as labelCls, th, td } from '../admin/ui';
import { Panel } from '../editorial/kit';
import { fmtDay, fmtPct } from '../budget/api';
import { ENGINE_ENABLED } from '../engine';
import { distApi, type TrackSummary } from './api';
import { Share, n0 } from './parts';

/** İzlenen kitaplar: onaydan sonraki 8 hafta plan → sevk → faturalanan → iade. Kitaba dokununca bölge, hafta, cari. */
export default function TrackingTab({ items, loading }: { items: TrackSummary[]; loading: boolean }) {
  const [open, setOpen] = useState<string | null>(null);
  if (loading) return <Panel><div className="py-8 text-center text-[12px] text-canvas-muted">Okunuyor…</div></Panel>;
  if (!items.length) {
    return (
      <Panel>
        <div className="py-8 text-center text-[12.5px] text-canvas-muted">İzlenen kitap yok. Onaylanan plan onay gününden itibaren 8 hafta burada izlenir.</div>
      </Panel>
    );
  }
  return (
    <div className="flex flex-col gap-2">
      {items.map((s) => (
        <Panel key={s.planId}>
          <button type="button" onClick={() => setOpen(open === s.stokKodu ? null : s.stokKodu)} aria-expanded={open === s.stokKodu} className="flex w-full flex-col gap-2 text-left">
            <div className="flex flex-wrap items-baseline justify-between gap-2">
              <div className="min-w-0">
                <div className="break-words text-[14px] font-extrabold">{s.ad ?? s.stokKodu}</div>
                <div className="text-[11.5px] text-canvas-muted">
                  <span className="font-mono">{s.stokKodu}</span> · onay {fmtDay(s.onay)} · {s.hafta}/{s.takipHafta}. hafta · {n0(s.musteri)} müşteri
                </div>
              </div>
              {s.veriBitti && <span className="text-[11.5px] font-bold text-amber-700">Logo verisi onaydan önce bitiyor</span>}
            </div>
            <div className="grid grid-cols-2 gap-2 text-[12px] sm:grid-cols-5">
              <Fig label="Plan" value={n0(s.plan)} />
              <Fig label="Sevk" value={n0(s.sevk)} sub={fmtPct(s.sevkOrani, 0)} />
              <Fig label="Faturalanan" value={n0(s.fatura)} />
              <Fig label="İade" value={n0(s.iade)} sub={fmtPct(s.iadeOrani, 0)} />
              <Fig label="Plan dışı sevk" value={n0(s.planDisi.sevk)} sub={`${n0(s.planDisi.musteri)} müşteri`} />
            </div>
            <Share value={s.sevkOrani} tone="emerald" />
          </button>
          {open === s.stokKodu && <Detail stok={s.stokKodu} planId={s.planId} />}
        </Panel>
      ))}
    </div>
  );
}

function Fig({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div>
      <div className={labelCls}>{label}</div>
      <div className="font-mono text-[15px] font-bold tabular-nums">{value}</div>
      {sub && <div className="text-[11px] text-canvas-muted">{sub}</div>}
    </div>
  );
}

function Detail({ stok, planId }: { stok: string; planId: string }) {
  const q = useQuery({ queryKey: ['dist', 'tracking', stok], queryFn: () => distApi.tracking(stok), enabled: ENGINE_ENABLED });
  const s = q.data?.items[0];
  if (q.error) return <Note tone="err">{errText(q.error, 'Takip okunamadı.')}</Note>;
  if (!s) return <div className="py-4 text-center text-[12px] text-canvas-muted">Okunuyor…</div>;
  return (
    <div className="mt-3 flex flex-col gap-3">
      <div className="flex flex-wrap items-center justify-between gap-2 text-[12px] text-canvas-muted">
        <span>Değerlendirme günü {fmtDay(s.degerlendirmeGunu)}</span>
        <Link to={`/ilk-dagilim/${encodeURIComponent(stok)}?plan=${planId}`} className="font-bold text-canvas-violet hover:underline">Planı aç</Link>
      </div>
      {!!s.haftalar?.length && (
        <div className="flex gap-1 overflow-x-auto">
          {s.haftalar.map((w) => (
            <div key={w.hafta} className="min-w-[76px] rounded-xl bg-slate-50 px-2 py-1.5 text-[11px]">
              <div className="font-bold">{w.hafta}. hafta</div>
              <div className="font-mono tabular-nums">sevk {n0(w.sevk)}</div>
              <div className="font-mono tabular-nums text-canvas-muted">iade {n0(w.iade)}</div>
            </div>
          ))}
        </div>
      )}
      <TableWrap>
        <thead>
          <tr>
            <th className={th}>Bölge</th>
            <th className={`${th} text-right`}>Plan</th>
            <th className={`${th} text-right`}>Sevk</th>
            <th className={`${th} text-right`}>Faturalanan</th>
            <th className={`${th} text-right`}>İade</th>
            <th className={`${th} text-right`}>Net</th>
          </tr>
        </thead>
        <tbody>
          {(s.bolgeler ?? []).map((r) => (
            <tr key={r.bolge} className="border-t border-slate-100">
              <td className={td}>{r.bolge}</td>
              <td className={`${td} text-right font-mono tabular-nums`}>{n0(r.plan)}</td>
              <td className={`${td} text-right font-mono tabular-nums`}>{n0(r.sevk)}</td>
              <td className={`${td} text-right font-mono tabular-nums`}>{n0(r.fatura)}</td>
              <td className={`${td} text-right font-mono tabular-nums`}>{n0(r.iade)}</td>
              <td className={`${td} text-right font-mono tabular-nums ${r.sevk > 0 && r.net <= 0 ? 'font-bold text-red-700' : ''}`}>{n0(r.net)}</td>
            </tr>
          ))}
        </tbody>
      </TableWrap>
      <TableWrap>
        <thead>
          <tr>
            <th className={th}>Müşteri</th>
            <th className={th}>Bölge</th>
            <th className={`${th} text-right`}>Plan</th>
            <th className={`${th} text-right`}>Sevk</th>
            <th className={`${th} text-right`}>Faturalanan</th>
            <th className={`${th} text-right`}>İade</th>
          </tr>
        </thead>
        <tbody>
          {(s.cariler ?? []).map((c) => (
            <tr key={c.no} className="border-t border-slate-100">
              <td className={td}>
                <div className="font-bold">{c.unvan}</div>
                <div className="font-mono text-[11px] text-canvas-muted">{c.cariKodu}{c.bmt ? ` · ${c.bmt}` : ''}</div>
              </td>
              <td className={td}>{c.bolge}</td>
              <td className={`${td} text-right font-mono tabular-nums`}>{n0(c.adet)}</td>
              <td className={`${td} text-right font-mono tabular-nums ${c.takip.sevk <= 0 ? 'text-amber-700' : ''}`}>{n0(c.takip.sevk)}</td>
              <td className={`${td} text-right font-mono tabular-nums`}>{n0(c.takip.fatura)}</td>
              <td className={`${td} text-right font-mono tabular-nums`}>{n0(c.takip.iade)}</td>
            </tr>
          ))}
        </tbody>
      </TableWrap>
    </div>
  );
}
