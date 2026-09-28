import { useState } from 'react';
import { Link } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { ENGINE_ENABLED } from '../engine';
import { Loading, Note, Pill, btnGhost, btnPrimary, errText } from '../admin/ui';
import { AskSheet } from '../budget/parts';
import { fieldApi, fmtDay, fmtMoney, type FieldMeta, type PaymentPlan } from './api';
import { Empty } from './parts';
import SqlInfo from '../components/SqlInfo';
import type { Kaynaklar } from '../components/sqlInfo';

/** Ödeme planları: Zeki AI kuralla önerir (tutar = vadesi geçmiş, taksit = aylık ödeme hızına göre), temsilci düzeltir ve
 *  onaya gönderir, yetkili (öneren/gönderen değil) onaylar ya da gerekçeyle geri çevirir. Kayıttır: müşteriyle anlaşma,
 *  Logo/CRM işlemi insanın. */

const TONE: Record<PaymentPlan['durum'], 'muted' | 'warn' | 'ok' | 'err'> = { taslak: 'muted', onayda: 'warn', onayli: 'ok', reddedildi: 'err' };

export default function PlansTab({ meta }: { meta: FieldMeta }) {
  const [durum, setDurum] = useState(meta.me.canApprovePlan ? 'onayda' : '');
  const q = useQuery({ queryKey: ['field', 'plans', durum], queryFn: () => fieldApi.plans({ durum }), enabled: ENGINE_ENABLED });
  const opts = [{ key: '', label: 'Hepsi' }, ...meta.planStates];
  const err = errText(q.error, 'Ödeme planları okunamadı.');
  return (
    <div className="flex flex-col gap-3">
      <div className="-mx-1 overflow-x-auto px-1">
        <div className="flex w-max min-w-full gap-1 rounded-2xl bg-slate-100 p-1" role="tablist" aria-label="Plan durumu">
          {opts.map((o) => (
            <button
              key={o.key || 'hepsi'}
              type="button"
              role="tab"
              aria-selected={durum === o.key}
              onClick={() => setDurum(o.key)}
              className={`min-h-11 shrink-0 whitespace-nowrap rounded-xl px-3 text-[12px] font-extrabold transition-colors duration-150 sm:min-h-9 ${
                durum === o.key ? 'bg-canvas-violet text-white shadow-md' : 'text-canvas-ink hover:bg-white/70'
              }`}
            >
              {o.label}
            </button>
          ))}
        </div>
      </div>
      {q.isLoading ? (
        <Loading />
      ) : err ? (
        <Note tone="err">{err}</Note>
      ) : (q.data?.items ?? []).length === 0 ? (
        <Empty>Bu durumda ödeme planı yok. Plan, müşteri brifingindeki «Ödeme planı öner» ile başlar.</Empty>
      ) : (
        <ul className="flex flex-col gap-2">
          {q.data!.items.map((p) => (
            <PlanCard key={p.id} p={p} meta={meta} k={q.data?.kaynaklar} />
          ))}
        </ul>
      )}
    </div>
  );
}

export function PlanCard({ p, meta, compact, k, alan = 'items' }: { p: PaymentPlan; meta: FieldMeta; compact?: boolean; k?: Kaynaklar; alan?: string }) {
  const qc = useQueryClient();
  const [ask, setAsk] = useState<null | 'approve' | 'reject'>(null);
  const done = (msg: string) => {
    toast.success(msg);
    setAsk(null);
    void qc.invalidateQueries({ queryKey: ['field'] });
  };
  const fail = (e: unknown) => toast.error(errText(e, 'İşlem yapılamadı.') ?? 'İşlem yapılamadı.');
  const submit = useMutation({ mutationFn: () => fieldApi.submitPlan(p.id), onSuccess: () => done('Onaya gönderildi'), onError: fail });
  const approve = useMutation({ mutationFn: (note: string) => fieldApi.approvePlan(p.id, note || undefined), onSuccess: () => done('Plan onaylandı'), onError: fail });
  const reject = useMutation({ mutationFn: (note: string) => fieldApi.rejectPlan(p.id, note), onSuccess: () => done('Plan geri çevrildi'), onError: fail });
  const me = meta.me.username;
  const canDecide = meta.me.canApprovePlan && p.durum === 'onayda' && p.oneren !== me && p.gonderen !== me;
  const diff = Math.round((p.taksitToplam - p.tutar) * 100) / 100;

  return (
    <li className="rounded-2xl border border-slate-100 bg-white/85 p-3">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          {!compact && (
            <Link to={`/saha/musteri/${encodeURIComponent(p.code)}`} className="block truncate text-[13.5px] font-extrabold hover:underline">
              {p.unvan || p.code}
            </Link>
          )}
          <div className="flex flex-wrap items-center gap-x-1 text-[11.5px] text-canvas-muted">
            {fmtMoney(p.tutar)} · {p.taksitler.length} taksit · öneren {p.oneren} · {fmtDay(p.olusturma)}
            {k && <SqlInfo k={k} alan={alan} row={p.id} label="Ödeme planı" />}
          </div>
        </div>
        <Pill tone={TONE[p.durum]}>{p.durumAd}</Pill>
      </div>
      <ol className="mt-2 grid grid-cols-2 gap-1 sm:grid-cols-3">
        {p.taksitler.map((t) => (
          <li key={t.sira} className="flex items-baseline justify-between gap-2 rounded-lg bg-slate-50 px-2 py-1 text-[12px]">
            <span className="text-canvas-muted">{fmtDay(t.tarih)}</span>
            <span className="font-mono font-bold tabular-nums">{fmtMoney(t.tutar)}</span>
          </li>
        ))}
      </ol>
      {diff !== 0 && <Note tone="warn">Taksitlerin toplamı vadesi geçmiş tutardan {fmtMoney(Math.abs(diff))} {diff > 0 ? 'fazla' : 'eksik'}.</Note>}
      {p.gerekce && <p className="mt-2 text-[11.5px] leading-snug text-canvas-muted">{p.gerekce}</p>}
      {p.kararNotu && (
        <p className="mt-1 text-[11.5px] leading-snug">
          <span className="font-bold">{p.onaylayan}:</span> {p.kararNotu}
        </p>
      )}
      <div className="mt-2 flex flex-wrap justify-end gap-2">
        {p.durum === 'taslak' && p.oneren === me && (
          <button type="button" className={btnPrimary} disabled={submit.isPending} onClick={() => submit.mutate()}>
            Onaya gönder
          </button>
        )}
        {canDecide && (
          <>
            <button type="button" className={btnGhost} onClick={() => setAsk('reject')}>
              Geri çevir
            </button>
            <button type="button" className={btnPrimary} onClick={() => setAsk('approve')}>
              Onayla
            </button>
          </>
        )}
      </div>
      <AskSheet
        open={ask !== null}
        title={ask === 'approve' ? 'Ödeme planını onayla' : 'Ödeme planını geri çevir'}
        message={
          ask === 'approve'
            ? 'Onay yalnız portalda kayda geçer; müşteriyle anlaşma ve Logo/CRM işlemi ayrıca yapılır.'
            : 'Geri çevirme nedeni temsilciye bildirim olarak gider.'
        }
        confirm={ask === 'approve' ? 'Onayla' : 'Geri çevir'}
        danger={ask === 'reject'}
        input={ask === 'approve' ? 'Not (isteğe bağlı)' : 'Neden'}
        required={ask === 'reject'}
        busy={approve.isPending || reject.isPending}
        onClose={() => setAsk(null)}
        onConfirm={(t) => (ask === 'approve' ? approve.mutate(t) : reject.mutate(t))}
      />
    </li>
  );
}
