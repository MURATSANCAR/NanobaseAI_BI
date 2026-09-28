import type { ReactNode } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Check, Handshake, X } from 'lucide-react';
import { ENGINE_ENABLED } from '../engine';
import { Loading, Note, Pill, btnGhost, btnPrimary, errText } from '../admin/ui';
import { schoolsApi, type DealerCandidate, type DealerLink } from './api';
import { fmtDay, fmtNum, invalidateSchools } from './parts';
import SqlInfo from '../components/SqlInfo';
import type { Kaynaklar } from '../components/sqlInfo';

/** Okulun bayisi: onaylı bağ (CRM'deki ortak ziyaretten, elle ya da onaylanan öneri), onay bekleyenler ve kuralın
 *  sıraladığı adaylar (gerekçesiyle). Onay açıkça verilen yetkiyle; temsilci yalnız önerir. */

export default function DealerPanel({ schoolId, canDealer, canVisit }: { schoolId: string; canDealer: boolean; canVisit: boolean }) {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ['schools', 'dealers', schoolId], queryFn: () => schoolsApi.dealers(schoolId), enabled: ENGINE_ENABLED });
  const fail = (e: unknown) => toast.error(errText(e, 'Kaydedilemedi.') ?? 'Kaydedilemedi.');
  const decide = useMutation({
    mutationFn: (a: { link: string; approve: boolean }) => schoolsApi.decideDealer(schoolId, a.link, a.approve),
    onSuccess: (_r, a) => {
      toast.success(a.approve ? 'Eşleşme onaylandı.' : 'Eşleşme reddedildi.');
      invalidateSchools(qc);
    },
    onError: fail,
  });
  const propose = useMutation({
    mutationFn: (code: string) => schoolsApi.addDealer(schoolId, code),
    onSuccess: (r) => {
      toast.success(r.state === 'onayli' ? 'Bayi bağlandı.' : 'Öneri onaya gönderildi.');
      invalidateSchools(qc);
    },
    onError: fail,
  });
  const d = q.data;
  const active = (d?.links ?? []).filter((l) => l.state !== 'reddedildi');
  return (
    <section className="glass-panel rounded-2xl p-3 shadow-glass-float sm:rounded-3xl sm:p-4">
      <h2 className="flex items-center gap-1 text-[11px] font-bold uppercase tracking-wide text-canvas-muted">
        Bayi
        <SqlInfo k={d?.kaynaklar} alan="links" label="Okul–bayi eşleşmeleri" />
      </h2>
      {q.error && <Note tone="err">{errText(q.error, 'Bayiler okunamadı.')}</Note>}
      {q.isLoading && <Loading />}
      {d && (
        <>
          {active.length === 0 && <p className="mt-2 text-[12px] text-canvas-muted">Bağlı bayi yok.</p>}
          <ul className="mt-2 space-y-1.5">
            {active.map((l) => (
              <LinkRow key={l.id} l={l} canDealer={canDealer} busy={decide.isPending} onDecide={(approve) => decide.mutate({ link: l.id, approve })} />
            ))}
          </ul>
          {!d.logoOk && <p className="mt-2 text-[11.5px] text-amber-800">Logo okunamadı: satış karması puana girmedi.</p>}
          {d.candidates.length > 0 && (
            <details className="mt-3" open={active.length === 0}>
              <summary className="min-h-11 cursor-pointer text-[12px] font-bold text-canvas-violet sm:min-h-0">
                Zeki AI önerisi: ildeki {d.candidates.length} bayi ve kitapçı
              </summary>
              <p className="mt-1 text-[11px] leading-snug text-canvas-muted">
                {d.rule} <SqlInfo k={d.kaynaklar} alan="candidates" label="Aday bayi puanı" />
              </p>
              <ul className="mt-2 space-y-1.5">
                {d.candidates.map((c) => (
                  <CandidateRow
                    key={c.code}
                    c={c}
                    k={d.kaynaklar}
                    canDealer={canDealer}
                    canVisit={canVisit}
                    busy={decide.isPending || propose.isPending}
                    onApprove={() => decide.mutate({ link: `c-${c.code}`, approve: true })}
                    onPropose={() => propose.mutate(c.code)}
                  />
                ))}
              </ul>
            </details>
          )}
        </>
      )}
    </section>
  );
}

export function LinkRow({
  l,
  canDealer,
  busy,
  onDecide,
  schoolLine,
  footer,
}: {
  l: DealerLink;
  canDealer: boolean;
  busy: boolean;
  onDecide: (a: boolean) => void;
  schoolLine?: string;
  footer?: ReactNode;
}) {
  return (
    <li className={`rounded-xl border px-3 py-2 ${l.state === 'oneri' ? 'border-canvas-violet/30 bg-canvas-violet/5' : 'border-slate-100 bg-white/85'}`}>
      {schoolLine && <div className="text-[12.5px] font-extrabold">{schoolLine}</div>}
      <div className="flex flex-wrap items-center gap-1.5">
        <Handshake aria-hidden className="h-4 w-4 text-canvas-violet" />
        <span className="text-[13px] font-bold">{l.name ?? l.code}</span>
        <Pill tone={l.state === 'onayli' ? 'ok' : 'violet'}>{l.stateLabel}</Pill>
        <Pill tone="muted">{l.sourceLabel}</Pill>
      </div>
      <div className="mt-0.5 text-[11.5px] text-canvas-muted">
        {[l.channel, l.ilce ?? l.il, l.phone].filter(Boolean).join(' · ')}
        {l.decidedBy ? ` · ${l.decidedBy}, ${fmtDay(l.decidedAt)}` : ''}
      </div>
      {l.reason && <p className="mt-1 whitespace-pre-line text-[12px] leading-snug">{l.reason}</p>}
      {canDealer && l.state === 'oneri' && (
        <div className="mt-2 flex gap-1.5">
          <button type="button" className={btnPrimary} disabled={busy} onClick={() => onDecide(true)}>
            <Check aria-hidden className="h-4 w-4" />
            Onayla
          </button>
          <button type="button" className={btnGhost} disabled={busy} onClick={() => onDecide(false)}>
            <X aria-hidden className="h-4 w-4" />
            Reddet
          </button>
        </div>
      )}
      {canDealer && l.state === 'onayli' && (
        <div className="mt-1.5">
          <button type="button" className={`${btnGhost} !min-h-9 text-[12px]`} disabled={busy} onClick={() => onDecide(false)}>
            Bağı kaldır
          </button>
        </div>
      )}
      {footer}
    </li>
  );
}

function CandidateRow({
  c,
  k,
  canDealer,
  canVisit,
  busy,
  onApprove,
  onPropose,
}: {
  c: DealerCandidate;
  k?: Kaynaklar;
  canDealer: boolean;
  canVisit: boolean;
  busy: boolean;
  onApprove: () => void;
  onPropose: () => void;
}) {
  return (
    <li className="rounded-xl border border-slate-100 bg-white/85 px-3 py-2">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="text-[12.5px] font-bold">{c.name ?? c.code}</div>
          <div className="text-[11.5px] text-canvas-muted">{[c.channel, c.ilce ?? c.il, c.phone, `kademe satışı ${fmtNum(c.gradeSales)}`].filter(Boolean).join(' · ')}</div>
        </div>
        <span className="flex shrink-0 items-center gap-0.5">
          <SqlInfo k={k} alan="candidates[]" row={c.code} label={`${c.name ?? c.code}: aday puanı ve kademe satışı`} />
          <span className="font-mono text-[12px] font-bold tabular-nums" title="Aday puanı">
            {Math.round(c.score)}
          </span>
        </span>
      </div>
      <p className="mt-1 text-[11.5px] leading-snug">{c.why.join(' · ')}</p>
      {c.warning && <p className="mt-1 text-[11.5px] font-semibold text-amber-800">{c.warning}</p>}
      {!c.linked && (canDealer || canVisit) && (
        <div className="mt-1.5">
          {canDealer ? (
            <button type="button" className={btnGhost} disabled={busy} onClick={onApprove}>
              <Check aria-hidden className="h-4 w-4" />
              Bu bayiyi bağla
            </button>
          ) : (
            <button type="button" className={btnGhost} disabled={busy} onClick={onPropose}>
              Onaya öner
            </button>
          )}
        </div>
      )}
      {c.linked && <p className="mt-1 text-[11px] font-semibold text-canvas-muted">Zaten bağlı ya da onayda.</p>}
    </li>
  );
}
