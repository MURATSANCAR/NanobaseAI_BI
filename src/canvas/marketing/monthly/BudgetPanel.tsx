import { useEffect, useState } from 'react';
import { useMutation } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Note, btnGhost, btnPrimary, errText, field, label as labelCls } from '../../admin/ui';
import { fmtMoney, fmtPct, parseNum } from '../api';
import { Block, SourceNote } from '../parts';
import { monthApi, type MonthView } from './api';

/** Bütçe ve öncelik: M46 ay hedef payı ve önceki ay oranıyla yeni kitap / backlist dağılımı. Tutarı kod hesaplar;
 *  müdür satır satır düzeltir (öneri korunur, düzeltme «onaylı» sütununda). */
export default function BudgetPanel({ view, editable, canSeeBudget, onSaved }: {
  view: MonthView;
  editable: boolean;
  canSeeBudget: boolean;
  onSaved: (v: MonthView) => void;
}) {
  const [draft, setDraft] = useState<Record<string, string>>({});
  const [frame, setFrame] = useState('');
  const [note, setNote] = useState('');
  const key = (s: string, k: string) => `${s}|${k}`;

  useEffect(() => {
    const d: Record<string, string> = {};
    view.budget.forEach((b) => { d[key(b.segment, b.kanal)] = b.onayli === null || b.onayli === undefined ? '' : String(b.onayli); });
    setDraft(d);
    const src = view.plan?.butceCerceveKaynak;
    setFrame(src?.kaynak === 'elle' && view.plan?.butceCerceve != null ? String(view.plan.butceCerceve) : '');
  }, [view]);

  const save = useMutation({
    mutationFn: () => monthApi.budget(view.donem, {
      items: view.budget.map((b) => ({ segment: b.segment, kanal: b.kanal, onayli: parseNum(draft[key(b.segment, b.kanal)] ?? '') })),
      cerceve: parseNum(frame),
      not: note || undefined,
    }),
    onSuccess: (v) => { onSaved(v); setNote(''); toast.success('Bütçe kaydedildi.'); },
    onError: (e) => toast.error(errText(e, 'Bütçe kaydedilemedi.') ?? ''),
  });

  const seg = view.hedef.segment ?? {};
  const prev = view.oncekiAy.segment ?? {};
  const bySeg = (s: string) => view.budget.filter((b) => b.segment === s).reduce((a, b) => a + (b.tutar ?? 0), 0);
  const total = view.budget.reduce((a, b) => a + (b.tutar ?? 0), 0);
  const src = view.plan?.butceCerceveKaynak;
  const zeki = view.plan?.zeki;

  return (
    <Block
      title="Bütçe ve öncelik"
      help="Segment payı = ayın satış hedefindeki payı × önceki ay hedefin altında kalındıysa açık kadar artış. Kanal payı o segmentin kitaplarına bağlı CRM pazarlama harcamasından. Rakamı kod hesaplar; Zeki AI yalnız gerekçe yazar."
    >
      {!view.hedef.planId && <Note tone="warn">{view.hedef.not ?? 'Bu ay için onaylı satış hedefi yok.'}</Note>}
      <div className="mt-2 grid grid-cols-1 gap-2 sm:grid-cols-2">
        {(['yeni', 'backlist'] as const).map((s) => (
          <div key={s} className="rounded-xl bg-white/70 p-3">
            <div className="text-[11px] font-bold uppercase tracking-wide text-canvas-muted">{s === 'yeni' ? 'Yeni kitap' : 'Backlist'}</div>
            <div className="mt-1 flex flex-wrap items-baseline gap-x-3 gap-y-1 text-[12.5px]">
              <span><b className="font-mono tabular-nums">{fmtPct(view.hedef.paylar?.[s] ?? null)}</b> hedef payı</span>
              {canSeeBudget && <span className="text-canvas-muted">{fmtMoney(seg[s]?.ciro ?? null)} ay hedefi</span>}
              <span className={prev[s]?.oran != null && prev[s].oran! < 0.8 ? 'font-bold text-red-700' : 'text-canvas-muted'}>
                önceki ay {fmtPct(prev[s]?.oran ?? null)}
              </span>
              {canSeeBudget && total > 0 && <span className="text-canvas-muted">bütçe payı {fmtPct(bySeg(s) / total)}</span>}
            </div>
          </div>
        ))}
      </div>

      {canSeeBudget ? (
        <>
          <p className="mt-3 text-[12px] leading-snug text-canvas-muted">
            Çerçeve {fmtMoney(view.plan?.butceCerceve ?? null)} · {src?.gerekce ?? 'çerçeve yok'}
          </p>
          <div className="mt-2 overflow-x-auto rounded-2xl border border-slate-100 bg-white/80">
            <table className="w-full min-w-[560px] text-[12px]">
              <thead>
                <tr className="text-left text-[11px] font-bold uppercase tracking-wide text-canvas-muted">
                  <th className="px-3 py-2">Segment</th>
                  <th className="px-3 py-2">Kanal</th>
                  <th className="px-3 py-2 text-right">Öneri</th>
                  <th className="px-3 py-2 text-right">Onaylanan</th>
                </tr>
              </thead>
              <tbody>
                {view.budget.map((b) => (
                  <tr key={key(b.segment, b.kanal)} className="border-t border-slate-100 align-top">
                    <td className="px-3 py-2 font-bold">{b.segmentAdi}</td>
                    <td className="px-3 py-2">
                      {b.kanalAdi}
                      {b.gerekce && <div className="mt-0.5 text-[11px] leading-snug text-canvas-muted">{b.gerekce}</div>}
                    </td>
                    <td className="px-3 py-2 text-right font-mono tabular-nums">{fmtMoney(b.oneri)}</td>
                    <td className="px-3 py-2 text-right">
                      {editable ? (
                        <input
                          aria-label={`${b.segmentAdi} · ${b.kanalAdi} onaylanan tutar`}
                          inputMode="decimal"
                          className={`${field} w-32 text-right font-mono tabular-nums`}
                          placeholder="öneri"
                          value={draft[key(b.segment, b.kanal)] ?? ''}
                          onChange={(e) => setDraft({ ...draft, [key(b.segment, b.kanal)]: e.target.value })}
                        />
                      ) : (
                        <span className="font-mono tabular-nums">{b.onayli != null ? fmtMoney(b.onayli) : '—'}</span>
                      )}
                    </td>
                  </tr>
                ))}
                {view.budget.length === 0 && (
                  <tr><td colSpan={4} className="px-3 py-4 text-canvas-muted">Bütçe satırı yok: kanal payı için CRM pazarlama harcaması okunamadı ya da hedef yok.</td></tr>
                )}
              </tbody>
              <tfoot>
                <tr className="border-t border-slate-200">
                  <td className="px-3 py-2 font-extrabold" colSpan={2}>Toplam</td>
                  <td className="px-3 py-2 text-right font-mono font-extrabold tabular-nums" colSpan={2}>{fmtMoney(view.plan?.butceToplam ?? null)}</td>
                </tr>
              </tfoot>
            </table>
          </div>
          {editable && (
            <div className="mt-3 grid grid-cols-1 gap-2 sm:grid-cols-[200px_1fr_auto] sm:items-end">
              <label className="flex flex-col gap-1">
                <span className={labelCls}>Ay çerçevesi (elle)</span>
                <input inputMode="decimal" className={`${field} font-mono tabular-nums`} placeholder="boş: kural" value={frame} onChange={(e) => setFrame(e.target.value)} />
              </label>
              <label className="flex flex-col gap-1">
                <span className={labelCls}>Düzeltmenin gerekçesi</span>
                <input className={field} value={note} onChange={(e) => setNote(e.target.value)} placeholder="Ör. eylülde backlist hedefin altında kaldı" />
              </label>
              <div className="flex gap-2">
                <button type="button" className={btnGhost} onClick={() => setDraft(Object.fromEntries(Object.keys(draft).map((k) => [k, ''])))}>Öneriye dön</button>
                <button type="button" className={btnPrimary} disabled={save.isPending} onClick={() => save.mutate()}>Kaydet</button>
              </div>
            </div>
          )}
        </>
      ) : (
        <p className="mt-3 text-[12px] text-canvas-muted">Bütçe tutarlarını görme yetkiniz yok; paylar görünür.</p>
      )}

      {zeki?.butceGerekce && (
        <div className="mt-3">
          <div className="text-[11px] font-bold uppercase tracking-wide text-canvas-muted">Zeki AI gerekçesi</div>
          <p className="mt-1 whitespace-pre-line text-[12.5px] leading-snug">{zeki.butceGerekce}</p>
        </div>
      )}
      <SourceNote text={view.oncekiAy.kaynak} sql={view.oncekiAy.sql} />
    </Block>
  );
}
