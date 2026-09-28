import { useState } from 'react';
import { Link } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { ENGINE_ENABLED } from '../engine';
import { Loading, Note, Pill, btnGhost, btnPrimary, errText } from '../admin/ui';
import { AskSheet } from '../budget/parts';
import { fmtDay, fmtMoney, fmtPct } from '../field/api';
import { Empty } from '../field/parts';
import { dealersApi, type DealersMeta, type Proposal } from './api';
import { SegmentBadge } from './parts';
import SqlInfo from '../components/SqlInfo';
import type { Kaynaklar } from '../components/sqlInfo';

/** Limit önerileri: kuraldan çıkan öneri → satış müdürü onaylar ya da gerekçeyle reddeder → onaylanan «CRM'e işlenecek»
 *  listesine düşer → CRM'e işleyen kişi «işlendi» der. Portal CRM'e yazmaz. */

const FILTERS = [
  { key: 'oneri', label: 'Onay bekleyen' },
  { key: 'onayli', label: "CRM'e işlenecek" },
  { key: 'crm_islendi', label: 'İşlendi' },
  { key: 'red', label: 'Reddedilen' },
  { key: 'gecersiz', label: 'Koşul kalkan' },
] as const;

const TONE: Record<Proposal['durum'], 'muted' | 'warn' | 'ok' | 'err' | 'violet'> = {
  oneri: 'warn', onayli: 'violet', crm_islendi: 'ok', red: 'err', gecersiz: 'muted',
};

export default function LimitsTab({ meta }: { meta: DealersMeta }) {
  const [durum, setDurum] = useState<string>('oneri');
  const q = useQuery({ queryKey: ['dealers', 'limits', durum], queryFn: () => dealersApi.limits({ durum }), enabled: ENGINE_ENABLED });
  const err = errText(q.error, 'Limit önerileri okunamadı.');
  return (
    <div className="flex flex-col gap-3">
      <div className="-mx-1 overflow-x-auto px-1">
        <div className="flex w-max min-w-full gap-1 rounded-2xl bg-slate-100 p-1" role="tablist" aria-label="Öneri durumu">
          {FILTERS.map((o) => (
            <button
              key={o.key}
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
      <Note tone="info">
        Öneriyi kural hesaplar (D segmentinde limit mevcut riske iner; A segmentinde dolu limit artırılır; limiti girilmemiş A/B carisine aylık alım kadar limit
        tanımlanır). Zeki AI yalnız gerekçe cümlesini yazar. Onay portalda kayda geçer; CRM'deki limiti müşteri temsilcisi elle değiştirir.
      </Note>
      {q.isLoading ? (
        <Loading />
      ) : err ? (
        <Note tone="err">{err}</Note>
      ) : (q.data?.items ?? []).length === 0 ? (
        <Empty>Bu durumda limit önerisi yok.</Empty>
      ) : (
        <ul className="flex flex-col gap-2">
          {q.data!.items.map((p) => (
            <ProposalCard key={p.id} p={p} meta={meta} k={q.data?.kaynaklar} />
          ))}
        </ul>
      )}
    </div>
  );
}

export function ProposalCard({ p, meta, compact, k, alan = 'items' }: { p: Proposal; meta: DealersMeta; compact?: boolean; k?: Kaynaklar; alan?: string }) {
  const qc = useQueryClient();
  const [ask, setAsk] = useState<null | 'approve' | 'reject'>(null);
  const done = (msg: string) => {
    toast.success(msg);
    setAsk(null);
    void qc.invalidateQueries({ queryKey: ['dealers'] });
  };
  const fail = (e: unknown) => toast.error(errText(e, 'İşlem yapılamadı.') ?? 'İşlem yapılamadı.');
  const approve = useMutation({ mutationFn: (n: string) => dealersApi.approveLimit(p.id, n || undefined), onSuccess: () => done("Onaylandı; CRM'e işlenecekler listesinde"), onError: fail });
  const reject = useMutation({ mutationFn: (n: string) => dealersApi.rejectLimit(p.id, n), onSuccess: () => done('Öneri reddedildi'), onError: fail });
  const crm = useMutation({ mutationFn: () => dealersApi.crmDone(p.id), onSuccess: () => done("CRM'e işlendi olarak kaydedildi"), onError: fail });
  const m = p.mevcut;
  return (
    <li className="rounded-2xl border border-slate-100 bg-white/85 p-3">
      <div className="flex items-start gap-2.5">
        <SegmentBadge segment={p.segment} skor={p.skor} />
        <div className="min-w-0 flex-1">
          <div className="flex items-start justify-between gap-2">
            {compact ? (
              <span className="text-[13.5px] font-extrabold">{p.degisimAd}</span>
            ) : (
              <Link to={`/bayi-risk/${encodeURIComponent(p.code)}`} className="min-w-0 truncate text-[13.5px] font-extrabold hover:underline">
                {p.unvan || p.code}
              </Link>
            )}
            <Pill tone={TONE[p.durum]}>{p.durumAd}</Pill>
          </div>
          <div className="mt-1 grid grid-cols-2 gap-1 text-[12px] sm:grid-cols-3">
            <span className="rounded-lg bg-slate-50 px-2 py-1">
              <span className="flex items-center gap-0.5 text-[10.5px] font-bold uppercase text-canvas-muted">
                CRM limit
                {k && <SqlInfo k={k} alan={alan} row={p.id} label="Öneri anındaki CRM limit ve risk" />}
              </span>
              <span className="font-mono font-bold tabular-nums">{m.limit_toplam ? fmtMoney(m.limit_toplam) : 'girilmemiş'}</span>
            </span>
            <span className="rounded-lg bg-slate-50 px-2 py-1">
              <span className="block text-[10.5px] font-bold uppercase text-canvas-muted">Risk</span>
              <span className="font-mono font-bold tabular-nums">
                {fmtMoney(m.risk_toplam ?? null)}
                {m.risk_doluluk !== null && m.risk_doluluk !== undefined ? ` · ${fmtPct(m.risk_doluluk)}` : ''}
              </span>
            </span>
            <span className="rounded-lg bg-violet-50 px-2 py-1">
              <span className="flex items-center gap-0.5 text-[10.5px] font-bold uppercase text-canvas-violet">
                {compact ? 'Önerilen' : p.degisimAd}
                {k && <SqlInfo k={k} alan={`${alan}[].onerilen`} row={p.id} label="Önerilen limit (kural)" />}
              </span>
              <span className="font-mono font-bold tabular-nums">{fmtMoney(p.onerilen)}</span>
            </span>
          </div>
          <p className="mt-2 text-[12px] leading-snug">{p.gerekceMetin || p.gerekceKural}</p>
          {p.gerekceMetin && <p className="mt-1 text-[11px] leading-snug text-canvas-muted">Kural: {p.gerekceKural}</p>}
          <p className="mt-1 text-[11px] text-canvas-muted">
            {fmtDay(p.gun)} · kural sürüm {p.kuralSurum}
            {p.kararVeren ? ` · karar ${p.kararVeren} ${fmtDay(p.kararAt)}` : ''}
            {p.crmIsleyen ? ` · CRM'e işleyen ${p.crmIsleyen} ${fmtDay(p.crmIslendiAt)}` : ''}
          </p>
          {p.kararNotu && <p className="mt-1 text-[11.5px] leading-snug">Not: {p.kararNotu}</p>}
          <div className="mt-2 flex flex-wrap justify-end gap-2">
            {p.durum === 'oneri' && meta.me.canLimit && (
              <>
                <button type="button" className={btnGhost} onClick={() => setAsk('reject')}>
                  Reddet
                </button>
                <button type="button" className={btnPrimary} onClick={() => setAsk('approve')}>
                  Onayla
                </button>
              </>
            )}
            {p.durum === 'onayli' && (meta.me.canLimit || meta.me.canAll) && (
              <button type="button" className={btnPrimary} disabled={crm.isPending} onClick={() => crm.mutate()}>
                CRM'e işlendi
              </button>
            )}
          </div>
        </div>
      </div>
      <AskSheet
        open={ask !== null}
        title={ask === 'approve' ? 'Limit önerisini onayla' : 'Limit önerisini reddet'}
        message={
          ask === 'approve'
            ? "Onay portalda kayda geçer ve öneri «CRM'e işlenecek» listesine düşer. CRM'deki limit elle değiştirilir."
            : 'Ret nedeni öneriyle birlikte saklanır.'
        }
        confirm={ask === 'approve' ? 'Onayla' : 'Reddet'}
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
