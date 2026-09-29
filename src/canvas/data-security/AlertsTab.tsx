import { useState } from 'react';
import { useInfiniteQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { ENGINE_ENABLED } from '../engine';
import { Note, Pill, btnGhost, errText } from '../admin/ui';
import { Panel } from '../editorial/kit';
import { AskSheet } from '../budget/parts';
import { SEVERITY, fmtAt, securityApi, type Alert, type SecurityMeta } from './api';
import SqlInfo from '../components/SqlInfo';
import { kaynakOf } from '../components/kaynakOf';
import { EmptyHint } from '../components/Explain';

const STATES = [
  { key: 'open', label: 'Açık' },
  { key: 'closed', label: 'Kapanmış' },
  { key: 'all', label: 'Hepsi' },
] as const;

/** Kural tabanlı güvenlik uyarıları: açık olanlar önce; «gerçek / gerçek değil» diye kapatılır (gerekçeyle). */
export default function AlertsTab({ meta }: { meta?: SecurityMeta }) {
  const qc = useQueryClient();
  const [state, setState] = useState<(typeof STATES)[number]['key']>('open');
  const [ask, setAsk] = useState<null | { alert: Alert; verdict: 'gercek' | 'gercek-degil' }>(null);
  const q = useInfiniteQuery({
    queryKey: ['security', 'alerts', state],
    queryFn: ({ pageParam }) => securityApi.alerts({ state, before: pageParam }),
    initialPageParam: null as number | null,
    getNextPageParam: (last) => (typeof last.next === 'number' ? last.next : undefined),
    enabled: ENGINE_ENABLED,
  });
  const items = q.data?.pages.flatMap((p) => p.items) ?? [];
  const counts = q.data?.pages[0]?.counts;
  const act = useMutation({
    mutationFn: (v: { id: number; body: Parameters<typeof securityApi.closeAlert>[1] }) => securityApi.closeAlert(v.id, v.body),
    onSuccess: (a) => {
      setAsk(null);
      qc.invalidateQueries({ queryKey: ['security'] });
      toast.success(a.state === 'closed' ? 'Uyarı kapatıldı.' : 'Uyarı yeniden açıldı.');
    },
    onError: (e) => toast.error(errText(e, 'Uyarı güncellenemedi.') ?? ''),
  });
  const canClose = !!meta?.me.canClose;

  return (
    <Panel>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="flex items-center gap-1 text-[16px] font-extrabold tracking-tight">
          Güvenlik uyarıları
          <SqlInfo k={kaynakOf(q.data?.pages[0])} alan="counts" label="Açık ve kapalı uyarı sayıları" />
        </h2>
        <div className="flex gap-1 rounded-xl bg-slate-100 p-1" role="radiogroup" aria-label="Durum">
          {STATES.map((s) => (
            <button
              key={s.key}
              type="button"
              role="radio"
              aria-checked={state === s.key}
              onClick={() => setState(s.key)}
              className={`min-h-11 rounded-lg px-3 text-[12px] font-extrabold transition-colors duration-150 sm:min-h-8 ${state === s.key ? 'bg-white shadow-sm' : 'text-canvas-muted'}`}
            >
              {s.label}
              {counts && s.key !== 'all' ? <span className="ml-1 font-mono tabular-nums">{counts[s.key]}</span> : null}
            </button>
          ))}
        </div>
      </div>
      {q.error && <div className="mt-2"><Note tone="err">{errText(q.error, 'Uyarılar okunamadı.')}</Note></div>}
      {q.data && !items.length && (
        <div className="mt-3">
          <EmptyHint
            title={state === 'open' ? 'Açık uyarı yok' : state === 'closed' ? 'Kapatılmış uyarı yok' : 'Henüz uyarı yok'}
            why={state === 'open' ? 'Şu an incelenmeyi bekleyen güvenlik uyarısı yok. Kurallar 5 dakikada bir yeniden koşar.' : 'Bir kural tuttuğunda uyarı burada listelenir.'}
          />
        </div>
      )}
      <ul className="mt-3 space-y-2">
        {items.map((a) => (
          <li key={a.id} className="rounded-xl border border-slate-100 bg-white/80 p-3">
            <div className="flex flex-wrap items-center gap-1.5">
              <Pill tone={SEVERITY[a.severity]?.tone ?? 'muted'}>{SEVERITY[a.severity]?.label ?? a.severity}</Pill>
              <span className="text-[12.5px] font-extrabold">{a.ruleLabel}</span>
              <span className="text-[11.5px] text-canvas-muted">{fmtAt(a.at)}</span>
              {a.state === 'closed' && (
                <Pill tone={a.verdict === 'gercek' ? 'err' : 'ok'}>{a.verdict === 'gercek' ? 'gerçek olay' : 'gerçek değil'}</Pill>
              )}
              {a.mailed === 'sent' && <Pill tone="muted">e-posta gitti</Pill>}
            </div>
            <p className="mt-1.5 break-words text-[12.5px] leading-snug">{a.summary}</p>
            {a.state === 'closed' && (
              <p className="mt-1 text-[11.5px] text-canvas-muted">
                {a.closedBy} · {fmtAt(a.closedAt)}{a.note ? ` — ${a.note}` : ''}
              </p>
            )}
            {canClose && (
              <div className="mt-2 flex flex-wrap gap-2">
                {a.state === 'open' ? (
                  <>
                    <button type="button" className={btnGhost} onClick={() => setAsk({ alert: a, verdict: 'gercek' })}>Gerçek olay, kapat</button>
                    <button type="button" className={btnGhost} onClick={() => setAsk({ alert: a, verdict: 'gercek-degil' })}>Gerçek değil, kapat</button>
                  </>
                ) : (
                  <button type="button" className={btnGhost} disabled={act.isPending} onClick={() => act.mutate({ id: a.id, body: { state: 'open' } })}>
                    Yeniden aç
                  </button>
                )}
              </div>
            )}
          </li>
        ))}
      </ul>
      {q.hasNextPage && (
        <div className="mt-3 flex justify-center">
          <button type="button" className={btnGhost} disabled={q.isFetchingNextPage} onClick={() => q.fetchNextPage()}>
            {q.isFetchingNextPage ? 'Yükleniyor…' : 'Daha eski uyarılar'}
          </button>
        </div>
      )}
      <AskSheet
        open={!!ask}
        title={ask?.verdict === 'gercek' ? 'Gerçek uyarı olarak kapat' : '«Gerçek değil» diye kapat'}
        message={<p className="text-canvas-muted">{ask?.alert.summary}</p>}
        confirm="Kapat"
        input={ask?.verdict === 'gercek' ? 'Ne yapıldı (isteğe bağlı)' : 'Neden gerçek değil (ör. zamanlanmış iş, bilinen deneme)'}
        required={ask?.verdict === 'gercek-degil'}
        busy={act.isPending}
        onClose={() => setAsk(null)}
        onConfirm={(note) => ask && act.mutate({ id: ask.alert.id, body: { state: 'closed', verdict: ask.verdict, note } })}
      />
    </Panel>
  );
}
