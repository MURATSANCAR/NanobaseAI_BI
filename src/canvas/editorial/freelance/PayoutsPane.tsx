import { useState } from 'react';
import { useMutation, useQuery } from '@tanstack/react-query';
import { useSearchParams } from 'react-router-dom';
import { toast } from 'sonner';
import { Check, Download, FilePlus2, FileSpreadsheet, Loader2, Undo2, X } from 'lucide-react';
import { freelanceApi, type FlPayable, type FlPayoutHead } from '../../engine';
import { Loading, Note, Pill, btnGhost, btnPrimary, errText, field, nf } from '../../admin/ui';
import { useCan } from '../../useAdmin';
import { Panel } from '../kit';
import { LogoMovements } from './PeoplePane';
import SqlInfo, { InfoLabel } from '../../components/SqlInfo';
import { ConfirmButton, Empty, FieldBox, PAYOUT_STATUS, day, q2, stamp, tl, todayIso, useFlRefresh, type FlCtx } from './shared';
import { xlsxUrl } from '../../components/excel';

/**
 * Hakediş: kabul edilmiş işler kişi başına bir belgede toplanır, satırlar o anki tutarla dondurulur.
 * Taslak → onay bekliyor → onaylandı → ödendi. Onaylayan hazırlayandan farklı kişi olmalı (iki göz); onay ve ödeme
 * kaydı ayrıca verilen yetkiyle yapılır. Ödeme Logo'da yapılır; burada tarih ve belge/açıklama tutulur.
 */

const FILTERS: Array<{ key: '' | Exclude<FlPayoutHead['status'], 'silindi'>; label: string }> = [
  { key: '', label: 'Hepsi' },
  { key: 'taslak', label: 'Taslak' },
  { key: 'onay', label: 'Onay bekliyor' },
  { key: 'onaylandi', label: 'Onaylandı' },
  { key: 'odendi', label: 'Ödendi' },
];

export default function PayoutsPane({ ctx }: { ctx: FlCtx }) {
  const [params, setParams] = useSearchParams();
  const open = params.get('hakedis');
  const [status, setStatus] = useState<'' | Exclude<FlPayoutHead['status'], 'silindi'>>(ctx.canApprove && (ctx.ov.payouts.onay?.count ?? 0) > 0 ? 'onay' : '');
  const payable = useQuery({ queryKey: ['fl', 'payable'], queryFn: freelanceApi.payable });
  const list = useQuery({ queryKey: ['fl', 'payouts', status], queryFn: () => freelanceApi.payouts({ status }), placeholderData: (p) => p });
  const setOpen = (id: string | null) => {
    const next = new URLSearchParams(params);
    if (id) next.set('hakedis', id);
    else next.delete('hakedis');
    setParams(next, { replace: true });
  };

  return (
    <div className="grid gap-3 lg:grid-cols-[minmax(0,1fr)_minmax(0,560px)] lg:items-start lg:gap-4">
      <div className="grid gap-3">
        <Panel>
          <h3 className="inline-flex items-center gap-1 text-[13px] font-extrabold">
            Ödenecek işler
            <SqlInfo k={payable.data?.kaynaklar} alan="items[]" label="Ödenecek işler" />
          </h3>
          <p className="mt-0.5 text-[11.5px] text-canvas-muted">Teslimi kabul edilmiş, henüz hakedişe girmemiş görevler.</p>
          {payable.error && <Note tone="err">{errText(payable.error, 'Okunamadı.')}</Note>}
          {payable.data && !payable.data.items.length && <Empty>Ödenecek iş yok.</Empty>}
          <ul className="mt-2 space-y-2">
            {payable.data?.items.map((g) => (
              <PayableGroup key={g.personId} ctx={ctx} g={g} onCreated={(id) => setOpen(id)} />
            ))}
          </ul>
        </Panel>

        <Panel>
          <div className="-mx-1 overflow-x-auto px-1">
            <div className="inline-flex gap-1">
              {FILTERS.map((f) => (
                <button
                  key={f.key}
                  type="button"
                  aria-pressed={status === f.key}
                  onClick={() => setStatus(f.key)}
                  className={`min-h-9 whitespace-nowrap rounded-xl px-2.5 text-[12px] font-extrabold transition-[background-color,color,transform] duration-150 ease-out active:scale-[0.97] ${
                    status === f.key ? 'bg-canvas-ink text-white' : 'bg-slate-100 text-canvas-ink hover:bg-slate-200'
                  }`}
                >
                  {f.label}
                  {f.key && list.data ? <span className="ml-1 font-mono text-[10.5px] opacity-75">{tl(list.data.totals[f.key])}</span> : null}
                </button>
              ))}
            </div>
          </div>
          {list.data && (
            <p className="mt-2 flex flex-wrap items-center gap-x-1 gap-y-0.5 text-[11.5px] text-canvas-muted">
              Durum toplamları
              <SqlInfo k={list.data.kaynaklar} alan="totals" label="Durum başına hakediş toplamı" />
              <span aria-hidden>·</span> belge tutarları
              <SqlInfo k={list.data.kaynaklar} alan="items[]" label="Hakedişler" />
            </p>
          )}
          {list.error && <Note tone="err">{errText(list.error, 'Hakedişler okunamadı.')}</Note>}
          {list.data && !list.data.items.length && <Empty>Bu durumda hakediş yok.</Empty>}
          <ul className="mt-2 space-y-1.5">
            {list.data?.items.map((h) => (
              <li key={h.id}>
                <button
                  type="button"
                  onClick={() => setOpen(h.id)}
                  aria-pressed={open === h.id}
                  className={`flex w-full items-center gap-2 rounded-2xl border px-3 py-2.5 text-left text-[12.5px] transition-[border-color,background-color,transform] duration-150 ease-out active:scale-[0.99] ${
                    open === h.id ? 'border-canvas-violet bg-white' : 'border-slate-100 bg-white/85 hover:bg-white'
                  }`}
                >
                  <span className="font-mono text-[12px] font-bold text-canvas-muted">#{h.no}</span>
                  <span className="min-w-0 flex-1">
                    <span className="block truncate font-bold">{h.personName}</span>
                    <span className="block truncate text-[11px] text-canvas-muted">
                      {h.status === 'odendi' ? `ödendi ${day(h.paidOn)} · ${h.paidRef}` : `hazırlayan ${h.createdBy}, ${stamp(h.createdAt)}`}
                    </span>
                  </span>
                  <Pill tone={PAYOUT_STATUS[h.status].tone}>{PAYOUT_STATUS[h.status].label}</Pill>
                  <span className="shrink-0 font-mono font-bold tabular-nums">{tl(h.total)}</span>
                </button>
              </li>
            ))}
          </ul>
        </Panel>
      </div>

      {open && (
        <div className="order-first lg:sticky lg:top-0 lg:order-none">
          <PayoutDetail ctx={ctx} id={open} onClose={() => setOpen(null)} />
        </div>
      )}
    </div>
  );
}

function PayableGroup({ ctx, g, onCreated }: { ctx: FlCtx; g: FlPayable; onCreated: (id: string) => void }) {
  const refresh = useFlRefresh();
  const [open, setOpen] = useState(false);
  const [picked, setPicked] = useState<string[]>(() => g.tasks.map((t) => t.id));
  const [note, setNote] = useState('');
  const sum = g.tasks.filter((t) => picked.includes(t.id)).reduce((a, t) => a + t.amount, 0);
  const create = useMutation({
    mutationFn: () => freelanceApi.createPayout({ personId: g.personId, taskIds: picked, note }),
    onSuccess: (r) => {
      toast.success(`Hakediş #${r.no} hazırlandı: ${tl(r.total)}.`);
      refresh();
      onCreated(r.id);
    },
    onError: (e) => toast.error(errText(e, 'Hakediş hazırlanamadı.')),
  });
  return (
    <li className="rounded-2xl border border-slate-100 bg-white/85">
      <button type="button" onClick={() => setOpen((v) => !v)} aria-expanded={open} className="flex w-full items-center gap-2 px-3 py-2.5 text-left text-[12.5px]">
        <span className="min-w-0 flex-1">
          <span className="block truncate font-bold">{g.personName}</span>
          <span className="block text-[11px] text-canvas-muted">{nf.format(g.tasks.length)} iş</span>
        </span>
        <span className="font-mono font-bold tabular-nums">{tl(g.total)}</span>
      </button>
      {open && (
        <div className="border-t border-slate-100 px-3 pb-3 pt-2">
          <ul className="space-y-1">
            {g.tasks.map((t) => (
              <li key={t.id}>
                <label className="flex items-center gap-2 text-[12px]">
                  {ctx.canManage && (
                    <input
                      type="checkbox"
                      checked={picked.includes(t.id)}
                      onChange={() => setPicked((p) => (p.includes(t.id) ? p.filter((x) => x !== t.id) : [...p, t.id]))}
                      className="h-5 w-5 shrink-0 accent-canvas-violet"
                    />
                  )}
                  <span className="min-w-0 flex-1 truncate">
                    {[t.bookTitle || t.packageTitle, t.title].filter(Boolean).join(' · ')}
                    <span className="ml-1 text-canvas-muted">
                      {q2(t.units)} {t.unit} · kabul {day(t.acceptedAt)}
                    </span>
                  </span>
                  <span className="shrink-0 font-mono font-semibold tabular-nums">{tl(t.amount)}</span>
                </label>
              </li>
            ))}
          </ul>
          {ctx.canManage && (
            <div className="mt-2 grid gap-2">
              <input value={note} onChange={(e) => setNote(e.target.value)} className={field} placeholder="Not (ör. Eylül işleri)" />
              <button type="button" className={btnPrimary} disabled={!picked.length || create.isPending} onClick={() => create.mutate()}>
                {create.isPending ? <Loader2 aria-hidden className="h-4 w-4 animate-spin" /> : <FilePlus2 aria-hidden className="h-4 w-4" />}
                {picked.length} iş ile hakediş hazırla · {tl(sum)}
              </button>
            </div>
          )}
        </div>
      )}
    </li>
  );
}

function PayoutDetail({ ctx, id, onClose }: { ctx: FlCtx; id: string; onClose: () => void }) {
  const refresh = useFlRefresh();
  const canExport = useCan('veri.disa-aktar');
  const payout = useQuery({ queryKey: ['fl', 'payout', id], queryFn: () => freelanceApi.payout(id) });
  const [note, setNote] = useState('');
  const [paidOn, setPaidOn] = useState(todayIso());
  const [paidRef, setPaidRef] = useState('');
  const act = useMutation({
    mutationFn: (a: 'submit' | 'return' | 'approve' | 'pay' | 'delete') => freelanceApi.payoutAction(id, a, a === 'pay' ? { paidOn, paidRef } : a === 'return' ? { note } : {}),
    onSuccess: (_r, a) => {
      toast.success(
        { submit: 'Onaya gönderildi.', return: 'Geri gönderildi.', approve: 'Hakediş onaylandı.', pay: 'Ödendi olarak işaretlendi.', delete: 'Taslak silindi; işler ödenecekler listesine döndü.' }[a],
      );
      setNote('');
      refresh();
      if (a === 'delete') onClose();
    },
    onError: (e) => toast.error(errText(e, 'İşlem yapılamadı.')),
  });

  if (payout.error) return <Panel><Note tone="err">{errText(payout.error, 'Hakediş okunamadı.')}</Note></Panel>;
  if (!payout.data) return <Panel><Loading /></Panel>;
  const h = payout.data;
  const me = ctx.ov.me.username.toLowerCase();
  const own = [h.createdBy, h.submittedBy].some((u) => (u ?? '').toLowerCase() === me);

  return (
    <Panel>
      <div className="text-[12.5px]">
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <h2 className="text-[18px] font-extrabold leading-tight tracking-tight">Hakediş #{h.no}</h2>
              <Pill tone={PAYOUT_STATUS[h.status].tone}>{PAYOUT_STATUS[h.status].label}</Pill>
            </div>
            <p className="mt-0.5 text-[12px] text-canvas-muted">
              {h.person.name}
              {h.person.logoCard ? ` · Logo cari ${h.person.logoCard}` : ' · Logo cari kodu girilmemiş'}
            </p>
          </div>
          <div className="flex shrink-0 gap-1.5">
            {canExport && (
              <>
                <a href={freelanceApi.payoutCsvUrl(h.id)} className={`${btnGhost} px-2.5`} aria-label="CSV indir" title="CSV indir">
                  <Download aria-hidden className="h-4 w-4" />
                </a>
                <a href={xlsxUrl(freelanceApi.payoutCsvUrl(h.id))} className={`${btnGhost} px-2.5`} aria-label="Excel indir" title="Excel indir">
                  <FileSpreadsheet aria-hidden className="h-4 w-4" />
                </a>
              </>
            )}
            <button type="button" onClick={onClose} aria-label="Hakedişi kapat" className={`${btnGhost} px-2.5`}>
              <X aria-hidden className="h-4 w-4" />
            </button>
          </div>
        </div>

        {h.returnNote && h.status === 'taslak' && <Note tone="warn">Geri gönderildi: {h.returnNote}</Note>}
        {h.note && <p className="mt-2 text-[12px] text-canvas-muted">{h.note}</p>}

        <div className="mt-3 overflow-x-auto rounded-xl border border-slate-100">
          <table className="w-full min-w-[440px] text-[12px]">
            <thead>
              <tr className="text-left text-[10.5px] font-bold uppercase tracking-wide text-canvas-muted">
                <th className="px-2.5 py-1.5">İş</th>
                <th className="px-2.5 py-1.5 text-right">
                  <InfoLabel k={h.kaynaklar} alan="lines[].units">Miktar</InfoLabel>
                </th>
                <th className="px-2.5 py-1.5 text-right">
                  <InfoLabel k={h.kaynaklar} alan="lines[].unitPrice">Birim</InfoLabel>
                </th>
                <th className="px-2.5 py-1.5 text-right">
                  <InfoLabel k={h.kaynaklar} alan="lines[].amount">Tutar</InfoLabel>
                </th>
              </tr>
            </thead>
            <tbody>
              {h.lines.map((l) => (
                <tr key={l.id} className="border-t border-slate-100">
                  <td className="px-2.5 py-1.5">{l.description}</td>
                  <td className="whitespace-nowrap px-2.5 py-1.5 text-right font-mono tabular-nums">
                    {q2(l.units)} {l.unit}
                  </td>
                  <td className="whitespace-nowrap px-2.5 py-1.5 text-right font-mono tabular-nums">{tl(l.unitPrice)}</td>
                  <td className="whitespace-nowrap px-2.5 py-1.5 text-right font-mono font-bold tabular-nums">{tl(l.amount)}</td>
                </tr>
              ))}
            </tbody>
            <tfoot>
              <tr className="border-t border-slate-200">
                <td colSpan={3} className="px-2.5 py-2 text-right font-bold">
                  <InfoLabel k={h.kaynaklar} alan="total">Toplam (KDV hariç)</InfoLabel>
                </td>
                <td className="whitespace-nowrap px-2.5 py-2 text-right font-mono text-[14px] font-extrabold tabular-nums">{tl(h.total)}</td>
              </tr>
            </tfoot>
          </table>
        </div>

        <ol className="mt-3 space-y-1 text-[11.5px] text-canvas-muted">
          <li>Hazırlayan {h.createdBy} · {stamp(h.createdAt)}</li>
          {h.submittedAt && <li>Onaya gönderen {h.submittedBy} · {stamp(h.submittedAt)}</li>}
          {h.approvedAt && <li>Onaylayan {h.approvedBy} · {stamp(h.approvedAt)}</li>}
          {h.paidOn && (
            <li className="font-semibold text-emerald-700">
              Ödendi {day(h.paidOn)} · {h.paidRef} · kaydeden {h.paidBy}
            </li>
          )}
        </ol>

        {h.status === 'taslak' && ctx.canManage && (
          <div className="mt-3 flex flex-wrap justify-end gap-1.5">
            <ConfirmButton confirm="Taslak silinsin mi?" onConfirm={() => act.mutate('delete')} disabled={act.isPending}>
              Taslağı sil
            </ConfirmButton>
            <button type="button" className={btnPrimary} onClick={() => act.mutate('submit')} disabled={act.isPending}>
              Onaya gönder
            </button>
          </div>
        )}

        {(h.status === 'onay' || h.status === 'onaylandi') && ctx.canApprove && (
          <div className="mt-3 grid gap-2 rounded-xl bg-slate-50 p-2.5">
            {h.status === 'onaylandi' && (
              <div className="grid gap-2 sm:grid-cols-[150px_minmax(0,1fr)]">
                <FieldBox label="Ödeme tarihi">
                  <input type="date" max={todayIso()} value={paidOn} onChange={(e) => setPaidOn(e.target.value)} className={field} />
                </FieldBox>
                <FieldBox label="Logo belge no / açıklama *">
                  <input value={paidRef} onChange={(e) => setPaidRef(e.target.value)} className={field} placeholder="Havale fiş no, makbuz no…" />
                </FieldBox>
              </div>
            )}
            <input value={note} onChange={(e) => setNote(e.target.value)} className={field} placeholder="Geri gönderme nedeni" />
            <div className="flex flex-wrap items-center justify-end gap-1.5">
              <button type="button" className={btnGhost} disabled={!note.trim() || act.isPending} onClick={() => act.mutate('return')}>
                <Undo2 aria-hidden className="h-4 w-4" />
                Geri gönder
              </button>
              {h.status === 'onay' && (
                <button type="button" className={btnPrimary} disabled={own || act.isPending} onClick={() => act.mutate('approve')} title={own ? 'Hazırladığınız hakedişi başka biri onaylamalı' : undefined}>
                  <Check aria-hidden className="h-4 w-4" />
                  Onayla
                </button>
              )}
              {h.status === 'onaylandi' && (
                <button type="button" className={btnPrimary} disabled={!paidRef.trim() || act.isPending} onClick={() => act.mutate('pay')}>
                  <Check aria-hidden className="h-4 w-4" />
                  Ödendi olarak işaretle
                </button>
              )}
            </div>
            {h.status === 'onay' && own && <p className="text-right text-[11px] text-amber-700">Bu hakedişi siz hazırladınız; onayı başka biri verir.</p>}
          </div>
        )}
        {h.status === 'onay' && !ctx.canApprove && <p className="mt-3 text-[11.5px] text-canvas-muted">Onay, hakediş onay yetkisi olan kişide bekliyor.</p>}

        {h.person.logoCard && <LogoMovements personId={h.person.id} />}
      </div>
    </Panel>
  );
}
