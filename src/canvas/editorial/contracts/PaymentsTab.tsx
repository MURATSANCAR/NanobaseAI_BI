import { useState, type ReactNode } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { CalendarPlus, Loader2, Plus } from 'lucide-react';
import { toast } from 'sonner';
import { Note, Pill, btnGhost, btnPrimary, field } from '../../admin/ui';
import { Panel } from '../kit';
import { contractApi, type Detail, type Meta, type Payment } from './api';
import { NumInput } from './TermsForm';
import { Field, Sheet, day, errMsg, money, today } from './ui';

/** Sözleşmenin ödeme takvimi: avans, tek ödeme, onaylı hakedişler ve diğer ödemeler; vade ve ödendi bilgisi. */

export const paymentTone = (p: Payment): 'ok' | 'warn' | 'err' | 'muted' =>
  p.status === 'odendi' ? 'ok' : p.status === 'iptal' ? 'muted' : p.overdue ? 'err' : 'warn';

function PaymentSheet({ d, meta, p, onClose }: { d: Detail; meta: Meta; p: Payment | null; onClose: () => void }) {
  const qc = useQueryClient();
  const [kind, setKind] = useState(p?.kind ?? 'diger');
  const [party, setParty] = useState(p?.party ?? d.terms.parties[0]?.name ?? '');
  const [dueOn, setDueOn] = useState(p?.dueOn ?? '');
  const [amount, setAmount] = useState<number | null>(p?.amount ?? null);
  const [currency, setCurrency] = useState(p?.currency ?? d.terms.currency);
  const [note, setNote] = useState(p?.note ?? '');
  const locked = p?.kind === 'hakedis';
  const save = useMutation({
    mutationFn: () =>
      p
        ? contractApi.paymentUpdate(p.id, locked ? { dueOn: dueOn || null, note } : { kind, party, dueOn: dueOn || null, amount, currency, note })
        : contractApi.paymentAdd(d.key, { kind, party, dueOn: dueOn || null, amount, currency, note }),
    onSuccess: () => {
      toast.success('Ödeme kaydedildi.');
      qc.invalidateQueries({ queryKey: ['contracts'] });
      onClose();
    },
  });
  return (
    <Sheet
      title={p ? 'Ödemeyi düzenle' : 'Ödeme ekle'}
      onClose={onClose}
      footer={
        <>
          <button type="button" className={btnGhost} onClick={onClose}>Vazgeç</button>
          <button type="button" className={btnPrimary} disabled={save.isPending || (!locked && amount == null)} onClick={() => save.mutate()}>
            {save.isPending && <Loader2 aria-hidden className="h-4 w-4 animate-spin" />}
            Kaydet
          </button>
        </>
      }
    >
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label="Tür">
          <select value={kind} disabled={locked} onChange={(e) => setKind(e.target.value as Payment['kind'])} className={field}>
            {Object.entries(meta.paymentKinds).filter(([k]) => k !== 'hakedis' || locked).map(([k, v]) => (
              <option key={k} value={k}>{v}</option>
            ))}
          </select>
        </Field>
        <Field label="Alacaklı">
          <input value={party} disabled={locked} onChange={(e) => setParty(e.target.value)} className={field} list="contract-parties" />
          <datalist id="contract-parties">
            {d.terms.parties.map((x) => (
              <option key={x.name} value={x.name} />
            ))}
          </datalist>
        </Field>
        <Field label="Vade">
          <input type="date" value={dueOn ?? ''} onChange={(e) => setDueOn(e.target.value)} className={field} />
        </Field>
        <Field label="Tutar" hint={locked ? 'Hakediş tutarı hakedişten gelir.' : undefined}>
          <div className="grid grid-cols-[minmax(0,1fr)_96px] gap-2">
            <NumInput value={amount} onChange={setAmount} />
            <select aria-label="Para birimi" value={currency} disabled={locked} onChange={(e) => setCurrency(e.target.value)} className={field}>
              {Object.entries(meta.currencies).map(([k, v]) => (
                <option key={k} value={k}>{v}</option>
              ))}
            </select>
          </div>
        </Field>
        <Field label="Not" wide>
          <input value={note} onChange={(e) => setNote(e.target.value)} className={field} />
        </Field>
      </div>
      {save.error && <div className="mt-3"><Note tone="err">{errMsg(save.error)}</Note></div>}
    </Sheet>
  );
}

export function PaidSheet({ p, onClose }: { p: Payment; onClose: () => void }) {
  const qc = useQueryClient();
  const [paidOn, setPaidOn] = useState(today());
  const [amount, setAmount] = useState<number | null>(p.amount);
  const [ref, setRef] = useState('');
  const pay = useMutation({
    mutationFn: () => contractApi.paymentPaid(p.id, { paidOn, paidAmount: amount, paidRef: ref }),
    onSuccess: () => {
      toast.success('Ödendi olarak işaretlendi.');
      qc.invalidateQueries({ queryKey: ['contracts'] });
      onClose();
    },
  });
  return (
    <Sheet
      title={`${p.kindLabel} ödendi`}
      onClose={onClose}
      footer={
        <>
          <button type="button" className={btnGhost} onClick={onClose}>Vazgeç</button>
          <button type="button" className={btnPrimary} disabled={pay.isPending || amount == null} onClick={() => pay.mutate()}>
            {pay.isPending && <Loader2 aria-hidden className="h-4 w-4 animate-spin" />}
            Ödendi
          </button>
        </>
      }
    >
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label="Ödeme tarihi">
          <input type="date" value={paidOn} onChange={(e) => setPaidOn(e.target.value)} className={field} />
        </Field>
        <Field label={`Ödenen tutar (${p.currency})`}>
          <NumInput value={amount} onChange={setAmount} />
        </Field>
        <Field label="Dekont / Logo fiş no" wide>
          <input value={ref} onChange={(e) => setRef(e.target.value)} className={field} />
        </Field>
      </div>
      {pay.error && <div className="mt-3"><Note tone="err">{errMsg(pay.error)}</Note></div>}
    </Sheet>
  );
}

export function PaymentRow({ p, onEdit, onPay, onCancel, canEdit, canPay, contract }: {
  p: Payment;
  onEdit?: () => void;
  onPay?: () => void;
  onCancel?: () => void;
  canEdit: boolean;
  canPay: boolean;
  contract?: ReactNode;
}) {
  return (
    <li className="rounded-2xl border border-slate-100 bg-white/85 p-3 text-[12.5px]">
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-extrabold">{p.kindLabel}</span>
        <Pill tone={paymentTone(p)}>{p.overdue ? 'Vadesi geçti' : p.statusLabel}</Pill>
        <span className="font-mono font-bold tabular-nums">{money(p.status === 'odendi' ? p.paidAmount : p.amount, p.currency)}</span>
        <span className="text-[11.5px] text-canvas-muted">
          {p.status === 'odendi' ? `ödendi ${day(p.paidOn)}${p.paidRef ? ` · ${p.paidRef}` : ''}` : `vade ${day(p.dueOn)}`}
          {p.party ? ` · ${p.party}` : ''}
        </span>
      </div>
      {contract && <div className="mt-1">{contract}</div>}
      {(p.note || p.periodStart) && (
        <p className="mt-1 whitespace-pre-wrap text-[11.5px] text-canvas-muted">{p.periodStart ? `Dönem ${day(p.periodStart)} – ${day(p.periodEnd)}. ` : ''}{p.note}</p>
      )}
      {p.status === 'planlandi' && (canEdit || canPay) && (
        <div className="mt-2 flex flex-wrap gap-1.5">
          {canPay && onPay && <button type="button" className={btnPrimary} onClick={onPay}>Ödendi işaretle</button>}
          {canEdit && onEdit && <button type="button" className={btnGhost} onClick={onEdit}>Düzenle</button>}
          {canEdit && onCancel && p.kind !== 'hakedis' && <button type="button" className={btnGhost} onClick={onCancel}>İptal et</button>}
        </div>
      )}
      {p.status === 'odendi' && canPay && onCancel && (
        <div className="mt-2">
          <button type="button" className={btnGhost} onClick={onCancel}>Ödeme kaydını iptal et</button>
        </div>
      )}
    </li>
  );
}

export default function PaymentsTab({ d, meta }: { d: Detail; meta: Meta }) {
  const qc = useQueryClient();
  const [edit, setEdit] = useState<Payment | 'new' | null>(null);
  const [paying, setPaying] = useState<Payment | null>(null);
  const plan = useMutation({
    mutationFn: () => contractApi.paymentPlan(d.key),
    onSuccess: (r) => {
      toast.success(r.added.length ? `Eklendi: ${r.added.join(', ')}` : 'Şartlardan eklenecek yeni ödeme yok.');
      qc.invalidateQueries({ queryKey: ['contracts'] });
    },
    onError: (e) => toast.error(errMsg(e) ?? 'Plan çıkarılamadı.'),
  });
  const cancel = useMutation({
    mutationFn: ({ p, note }: { p: Payment; note?: string }) => contractApi.paymentCancel(p.id, note),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['contracts'] }),
    onError: (e) => toast.error(errMsg(e) ?? 'İptal edilemedi.'),
  });
  const askCancel = (p: Payment) => {
    const note = window.prompt(p.status === 'odendi' ? 'Ödenmiş kaydın iptal gerekçesi (zorunlu):' : 'İptal gerekçesi (isteğe bağlı):', '');
    if (note === null) return;
    cancel.mutate({ p, note: note || undefined });
  };
  const open = d.payments.filter((p) => p.status === 'planlandi');
  const byCur = open.reduce<Record<string, number>>((acc, p) => ({ ...acc, [p.currency]: (acc[p.currency] ?? 0) + (p.amount ?? 0) }), {});
  const hakedisDone = new Set(d.statements.filter((s) => s.status === 'onaylandi').map((s) => s.periodStart));
  const upcoming = d.periods.filter((x) => !hakedisDone.has(x.periodStart)).slice(-4);
  return (
    <div className="grid gap-3 lg:grid-cols-[minmax(0,1fr)_320px]">
      <Panel>
        <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
          <div className="text-[12.5px]">
            <span className="font-extrabold">Bekleyen: </span>
            {Object.keys(byCur).length ? Object.entries(byCur).map(([c, v]) => money(v, c)).join(' · ') : 'yok'}
          </div>
          {d.can.edit && d.status !== 'iptal' && (
            <div className="flex flex-wrap gap-1.5">
              <button type="button" className={btnGhost} disabled={plan.isPending} onClick={() => plan.mutate()}>
                {plan.isPending ? <Loader2 aria-hidden className="h-4 w-4 animate-spin" /> : <CalendarPlus aria-hidden className="h-4 w-4" />}
                Şartlardan plan çıkar
              </button>
              <button type="button" className={btnPrimary} onClick={() => setEdit('new')}>
                <Plus aria-hidden className="h-4 w-4" />
                Ödeme ekle
              </button>
            </div>
          )}
        </div>
        {!d.payments.length && <p className="py-6 text-center text-[12.5px] text-canvas-muted">Ödeme planı yok. «Şartlardan plan çıkar» avans ve tek ödemeyi ekler; hakedişler onaylandıkça gelir.</p>}
        <ul className="space-y-2">
          {d.payments.map((p) => (
            <PaymentRow key={p.id} p={p} canEdit={d.can.edit} canPay={d.can.finance} onEdit={() => setEdit(p)} onPay={() => setPaying(p)} onCancel={() => askCancel(p)} />
          ))}
        </ul>
      </Panel>
      <Panel>
        <h3 className="text-[13px] font-extrabold">Hakediş dönemleri</h3>
        {!d.periods.length ? (
          <p className="mt-1 text-[12px] text-canvas-muted">Bu sözleşmede dönemsel hakediş yok ({meta.paymentTypes[d.terms.paymentType] ?? d.terms.paymentType}) ya da başlangıç tarihi girilmemiş.</p>
        ) : (
          <>
            <p className="mt-1 text-[11.5px] text-canvas-muted">{d.terms.periodMonths} ayda bir, dönem sonundan {d.terms.paymentDays ?? 30} gün sonra ödenir.</p>
            <ul className="mt-2 space-y-1 text-[12px]">
              {upcoming.map((x) => (
                <li key={x.periodStart} className="flex justify-between gap-2 border-b border-slate-100 py-1 last:border-0">
                  <span>{day(x.periodStart)} – {day(x.periodEnd)}</span>
                  <span className="font-mono tabular-nums text-canvas-muted">vade {day(x.dueOn)}</span>
                </li>
              ))}
            </ul>
            <p className="mt-2 text-[11.5px] text-canvas-muted">Onaylı hakedişi olan dönemler listede görünmez.</p>
          </>
        )}
      </Panel>
      {edit && <PaymentSheet d={d} meta={meta} p={edit === 'new' ? null : edit} onClose={() => setEdit(null)} />}
      {paying && <PaidSheet p={paying} onClose={() => setPaying(null)} />}
    </div>
  );
}
