import { useEffect, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Loader2, Sparkles } from 'lucide-react';
import Sheet from '../editorial/studio/reader/Sheet';
import { Loading, Note, Pill, btnGhost, btnPrimary, errText, field, label as labelCls } from '../admin/ui';
import { NOTIFY, fmtAt, fmtMinutes, fmtMs, itOpsApi, type IncidentDetail } from './api';

/** Olay ayrıntısı: tarif, zaman çizelgesi, kök neden notu, Zeki AI değerlendirme taslağı ve yayımı. */
export default function IncidentPanel({ id, canClose, onClose }: { id: string | null; canClose: boolean; onClose: () => void }) {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ['itops', 'incident', id], queryFn: () => itOpsApi.incident(id as string), enabled: !!id });
  const inc = q.data;
  const [cause, setCause] = useState('');
  const [draft, setDraft] = useState('');
  useEffect(() => {
    setCause(inc?.rootCause ?? '');
    setDraft(inc?.postmortemDraft ?? '');
  }, [inc?.id, inc?.rootCause, inc?.postmortemDraft]);

  const done = (out: IncidentDetail, msg: string) => {
    qc.setQueryData(['itops', 'incident', id], out);
    qc.invalidateQueries({ queryKey: ['itops', 'status'] });
    qc.invalidateQueries({ queryKey: ['itops', 'incidents'] });
    toast.success(msg);
  };
  const save = useMutation({
    mutationFn: (b: { rootCause?: string; falseAlarm?: boolean; postmortem?: string; publish?: boolean }) => itOpsApi.updateIncident(id as string, b),
    onSuccess: (out, b) => done(out, b.publish ? 'Değerlendirme yayımlandı.' : 'Kaydedildi.'),
    onError: (e) => toast.error(errText(e, 'Kaydedilemedi.') ?? ''),
  });
  const ai = useMutation({
    mutationFn: () => itOpsApi.draft(id as string),
    onSuccess: (out) =>
      done(
        out,
        out.draftSource === 'kural'
          ? 'Zeki AI metni olay kaydıyla tutmayan sayı içerdi; taslak kurala göre olay kaydından yazıldı. Düzeltip kaydedin.'
          : 'Zeki AI taslağı hazır; düzeltip kaydedin.',
      ),
    onError: (e) => toast.error(errText(e, 'Taslak yazılamadı.') ?? ''),
  });

  return (
    <Sheet
      open={!!id}
      modal
      wide
      onClose={onClose}
      title={inc ? `${inc.ringLabel} · ${inc.kindLabel}` : 'Olay'}
      subtitle={inc ? `${fmtAt(inc.openedAt)} → ${inc.closedAt ? fmtAt(inc.closedAt) : 'sürüyor'} · ${fmtMinutes(inc.minutes)}` : undefined}
    >
      {q.isLoading && <Loading />}
      {q.error && <Note tone="err">{errText(q.error, 'Olay açılamadı.')}</Note>}
      {inc && (
        <div className="flex flex-col gap-4 text-[13px] leading-snug">
          <div className="flex flex-wrap gap-1.5">
            <Pill tone={inc.open ? (inc.kind === 'kopma' ? 'err' : 'warn') : 'ok'}>{inc.open ? 'Açık' : 'Kapandı'}</Pill>
            {inc.notifyStatus && <Pill tone={inc.notifyStatus === 'sent' ? 'muted' : 'warn'}>Açılış: {NOTIFY[inc.notifyStatus] ?? inc.notifyStatus}</Pill>}
            {inc.closedNotify && <Pill tone="muted">Düzelme: {NOTIFY[inc.closedNotify] ?? inc.closedNotify}</Pill>}
            {inc.falseAlarm && <Pill tone="muted">Gerçek değil</Pill>}
          </div>

          <section className="rounded-2xl bg-slate-50 p-3">
            <h3 className={labelCls}>Ne yapmalı</h3>
            <p className="mt-1 font-semibold">{inc.recipe}</p>
          </section>

          <section>
            <h3 className={labelCls}>Hata</h3>
            <p className="mt-1 break-words">{inc.lastError ?? inc.firstError ?? '—'}</p>
            {inc.firstError && inc.firstError !== inc.lastError && <p className="mt-1 break-words text-[12px] text-canvas-muted">İlk: {inc.firstError}</p>}
          </section>

          <section>
            <h3 className={labelCls}>Denemeler ({inc.timeline.length})</h3>
            <ol className="mt-1 max-h-64 divide-y divide-slate-100 overflow-y-auto rounded-xl border border-slate-100">
              {inc.timeline.map((c) => (
                <li key={c.id} className="flex items-start gap-2 px-2.5 py-1.5 text-[12px]">
                  <span aria-hidden className={`mt-1 h-2 w-2 shrink-0 rounded-full ${c.ok === true ? 'bg-emerald-500' : c.ok === false ? 'bg-red-500' : 'bg-slate-300'}`} />
                  <span className="w-24 shrink-0 tabular-nums text-canvas-muted">{fmtAt(c.at)}</span>
                  <span className="min-w-0 flex-1 break-words">{c.detail}</span>
                  <span className="shrink-0 tabular-nums text-canvas-muted">{fmtMs(c.latencyMs)}</span>
                </li>
              ))}
              {!inc.timeline.length && <li className="px-2.5 py-2 text-[12px] text-canvas-muted">Kayıtlı deneme yok.</li>}
            </ol>
          </section>

          <section className="flex flex-col gap-2">
            <label className="flex flex-col gap-1">
              <span className={labelCls}>Kök neden notu</span>
              <textarea className={`${field} min-h-[80px]`} value={cause} disabled={!canClose} onChange={(e) => setCause(e.target.value)}
                placeholder={canClose ? 'Ne oldu, neden oldu, ne yapıldı' : 'Henüz not yok.'} />
            </label>
            {inc.rootCauseBy && <span className="text-[11.5px] text-canvas-muted">{inc.rootCauseBy} · {fmtAt(inc.rootCauseAt)}</span>}
            {canClose && (
              <div className="flex flex-wrap gap-2">
                <button type="button" className={btnPrimary} disabled={save.isPending || cause === (inc.rootCause ?? '')} onClick={() => save.mutate({ rootCause: cause })}>
                  Notu kaydet
                </button>
                <button type="button" className={btnGhost} disabled={save.isPending} onClick={() => save.mutate({ falseAlarm: !inc.falseAlarm })}>
                  {inc.falseAlarm ? 'Gerçek olay olarak işaretle' : 'Gerçek değil (yanlış alarm)'}
                </button>
              </div>
            )}
          </section>

          <section className="flex flex-col gap-2 border-t border-slate-100 pt-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <h3 className={labelCls}>Olay değerlendirmesi</h3>
              <Pill tone={inc.postmortemStatus === 'yayında' ? 'ok' : inc.postmortemStatus === 'taslak' ? 'warn' : 'muted'}>
                {inc.postmortemStatus === 'yok' ? 'Yazılmadı' : inc.postmortemStatus === 'taslak' ? 'Taslak' : 'Yayında'}
              </Pill>
            </div>
            {canClose ? (
              <>
                <textarea className={`${field} min-h-[140px]`} value={draft} onChange={(e) => setDraft(e.target.value)}
                  placeholder="Ne oldu · Etki · Süre · Olası neden · Önerilen önlem" />
                <p className="text-[11.5px] text-canvas-muted">Zeki AI yalnız metni yazar; süre ve sayılar olay kaydından gelir, kayıtta olmayan sayı içeren metin atılıp kurala göre taslak konur. Yayımlamadan önce düzeltin.</p>
                <div className="flex flex-wrap gap-2">
                  <button type="button" className={btnGhost} disabled={ai.isPending} onClick={() => ai.mutate()}>
                    {ai.isPending ? <Loader2 aria-hidden className="h-4 w-4 animate-spin" /> : <Sparkles aria-hidden className="h-4 w-4" />}
                    Zeki AI taslağı
                  </button>
                  <button type="button" className={btnGhost} disabled={save.isPending || draft === (inc.postmortemDraft ?? '')} onClick={() => save.mutate({ postmortem: draft })}>
                    Taslağı kaydet
                  </button>
                  <button type="button" className={btnPrimary} disabled={save.isPending || inc.open || !draft.trim()}
                    title={inc.open ? 'Olay kapanınca yayımlanır' : undefined} onClick={() => save.mutate({ postmortem: draft, publish: true })}>
                    Yayımla
                  </button>
                </div>
              </>
            ) : (
              <p className="whitespace-pre-wrap">{inc.postmortemStatus === 'yayında' ? inc.postmortemDraft : 'Yayımlanmış değerlendirme yok.'}</p>
            )}
            {inc.postmortemBy && <span className="text-[11.5px] text-canvas-muted">{inc.postmortemBy} yayımladı · {fmtAt(inc.postmortemAt)}</span>}
          </section>
        </div>
      )}
    </Sheet>
  );
}
