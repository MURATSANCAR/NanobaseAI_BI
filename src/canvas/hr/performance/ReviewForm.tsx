import { useEffect, useState } from 'react';
import { useLocation, useParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Sparkles } from 'lucide-react';
import { ENGINE_ENABLED } from '../../engine';
import { Loading, Note, Pill, btnGhost, btnPrimary, errText, field, label as labelCls } from '../../admin/ui';
import { fmtDay, fmtDateTime } from '../hrApi';
import { Block, HrFrame } from '../parts';
import { GoalRow } from './parts';
import { REVIEW_TONE, perfApi, type Answers, type Review, type Section } from './perfApi';

/** M56 Değerlendirme formu: öz değerlendirme → yönetici değerlendirmesi → görüşme ve paylaşım → çalışan yorumu/itirazı →
 *  İK onayı. Aynı ekran üç yoldan açılır (Performansım, Ekibim, Değerlendirme dönemi); köprü rolü belirler. Yöneticinin
 *  bölümü paylaşılana kadar çalışana görünmez. Telefonda tek sütun. */

export default function ReviewForm() {
  const { id = '' } = useParams();
  const loc = useLocation();
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ['hr', 'perf', 'review', id], queryFn: () => perfApi.review(id), enabled: ENGINE_ENABLED && !!id });
  const r = q.data;
  const back = loc.pathname.startsWith('/ik/performansim') ? { to: '/ik/performansim', label: 'Performansım' }
    : loc.pathname.startsWith('/ik/ekibim') ? { to: '/ik/ekibim', label: 'Ekibim' } : { to: '/ik/degerlendirme', label: 'Değerlendirme dönemi' };
  const crumb = back.label;
  const set = (x: Review) => { qc.setQueryData(['hr', 'perf', 'review', id], x); void qc.invalidateQueries({ queryKey: ['hr', 'perf', 'me'] }); };
  return (
    <HrFrame crumb={crumb} detail={r?.employeeName ?? undefined} back={back} title={r ? `${r.employeeName} · ${r.cycle.name}` : 'Değerlendirme'}
      lead={r ? `${r.unitName ?? 'Birimsiz'} · Yönetici: ${r.managerName ?? 'kayıtlı değil'} · Değerlendirilen dönem ${fmtDay(r.cycle.periodStart)} – ${fmtDay(r.cycle.periodEnd)}` : ''}
      aside={r ? <div className="flex justify-start lg:justify-end"><Pill tone={REVIEW_TONE[r.state]}>{r.stateLabel}</Pill></div> : undefined}>
      {q.error && <Note tone="err">{errText(q.error, 'Değerlendirme açılamadı.')}</Note>}
      {q.isLoading && <Loading />}
      {r && <Body r={r} onChange={set} />}
    </HrFrame>
  );
}

function Body({ r, onChange }: { r: Review; onChange: (x: Review) => void }) {
  const form = r.cycle.form;
  const [self, setSelf] = useState<Answers>(r.self ?? { ratings: {}, notes: {} });
  const [mgr, setMgr] = useState<Answers>(r.manager ?? { ratings: {}, notes: {} });
  useEffect(() => { setSelf(r.self ?? { ratings: {}, notes: {} }); setMgr(r.manager ?? { ratings: {}, notes: {} }); }, [r.id, r.selfSubmittedAt, r.managerSubmittedAt]);
  const saveDraft = useMutation({
    mutationFn: () => perfApi.saveReview(r.id, r.can.editSelf ? { self } : { manager: mgr }),
    onSuccess: (x) => { toast.success('Taslak kaydedildi.'); onChange(x); },
    onError: (e) => toast.error(errText(e, 'Kaydedilemedi.')),
  });
  const submit = useMutation({
    mutationFn: () => (r.can.editSelf ? perfApi.submitSelf(r.id, self) : perfApi.submitManager(r.id, mgr)),
    onSuccess: (x) => { toast.success('Teslim edildi.'); onChange(x); },
    onError: (e) => toast.error(errText(e, 'Teslim edilemedi.')),
  });
  if (!form) return <Note tone="warn">Dönemin formu yok.</Note>;
  const editing = r.can.editSelf || r.can.editManager;
  const labels = form.overallLabels;
  return (
    <div className="flex flex-col gap-3">
      {r.role === 'self' && !r.sharedAt && r.managerSubmittedAt && <Note tone="info">Yöneticiniz değerlendirmesini yazdı; görüşmede sizinle paylaşınca burada görünecek.</Note>}
      {form.sections.map((s) => (
        <SectionBlock key={s.key} s={s} r={r} self={self} mgr={mgr} setSelf={setSelf} setMgr={setMgr} />
      ))}
      {(r.can.editManager || (r.manager && r.manager.overall)) && (
        <Block title="Genel değerlendirme (yönetici)" help="Kalibrasyonda birim dağılımı bu puandan çıkar. Sistem puan vermez.">
          <div className="grid grid-cols-1 gap-1.5 sm:grid-cols-5">
            {labels.map((l, i) => (
              <label key={l} className={`flex min-h-11 cursor-pointer items-center gap-2 rounded-xl px-3 py-2 text-[12.5px] font-semibold ${mgr.overall === i + 1 ? 'bg-canvas-violet text-white' : 'bg-white/80'}`}>
                <input type="radio" className="sr-only" name="overall" disabled={!r.can.editManager} checked={mgr.overall === i + 1} onChange={() => setMgr({ ...mgr, overall: i + 1 })} />
                <span className="font-mono">{i + 1}</span>{l}
              </label>
            ))}
          </div>
        </Block>
      )}
      {editing && (
        <div className="sticky bottom-0 z-10 flex flex-wrap justify-end gap-2 rounded-2xl bg-white/90 p-2 shadow-glass-float backdrop-blur">
          <button type="button" className={btnGhost} disabled={saveDraft.isPending} onClick={() => saveDraft.mutate()}>Taslak kaydet</button>
          <button type="button" className={btnPrimary} disabled={submit.isPending || (r.can.editManager && !mgr.overall)} onClick={() => submit.mutate()}>
            {r.can.editSelf ? 'Öz değerlendirmeyi teslim et' : 'Değerlendirmeyi teslim et'}
          </button>
        </div>
      )}
      <FlowBox r={r} onChange={onChange} />
      {(r.can.workSummary || r.workSummaries.length > 0) && <WorkBox r={r} onChange={onChange} />}
    </div>
  );
}

function SectionBlock({ s, r, self, mgr, setSelf, setMgr }: {
  s: Section; r: Review; self: Answers; mgr: Answers; setSelf: (a: Answers) => void; setMgr: (a: Answers) => void;
}) {
  const showMgr = r.manager !== null;
  return (
    <Block title={s.title} help={s.help}>
      {s.kind === 'hedef' && (
        <ul className="mb-2 flex flex-col gap-1.5">
          {!r.goals.length && <li className="text-[12px] text-canvas-muted">Bu dönemde yürürlükte hedef yok.</li>}
          {r.goals.map((g) => <li key={g.id}><GoalRow g={g} onOpen={() => undefined} /></li>)}
        </ul>
      )}
      {s.kind === 'yetkinlik' && (
        <ul className="flex flex-col gap-2">
          {s.items.map((it) => (
            <li key={it.key} className="rounded-xl bg-white/80 p-2.5">
              <div className="text-[13px] font-bold">{it.label}</div>
              <div className="mt-1 grid grid-cols-1 gap-2 sm:grid-cols-2">
                <Scale label="Çalışan" value={self.ratings[it.key]} disabled={!r.can.editSelf} onPick={(v) => setSelf({ ...self, ratings: { ...self.ratings, [it.key]: v } })} />
                {showMgr && <Scale label="Yönetici" value={mgr.ratings[it.key]} disabled={!r.can.editManager} onPick={(v) => setMgr({ ...mgr, ratings: { ...mgr.ratings, [it.key]: v } })} />}
              </div>
            </li>
          ))}
        </ul>
      )}
      <div className="mt-2 grid grid-cols-1 gap-2 lg:grid-cols-2">
        <NoteField label="Çalışanın notu" value={self.notes[s.key] ?? ''} disabled={!r.can.editSelf} onChange={(v) => setSelf({ ...self, notes: { ...self.notes, [s.key]: v } })} />
        {showMgr && (
          <NoteField label="Yöneticinin notu" value={mgr.notes[s.key] ?? ''} disabled={!r.can.editManager}
            onChange={(v) => setMgr({ ...mgr, notes: { ...mgr.notes, [s.key]: v } })} rewriteId={r.can.rewrite ? r.id : undefined} />
        )}
      </div>
    </Block>
  );
}

function Scale({ label, value, disabled, onPick }: { label: string; value?: number; disabled: boolean; onPick: (v: number) => void }) {
  return (
    <div role="radiogroup" aria-label={label} className="flex items-center gap-1">
      <span className="w-16 shrink-0 text-[11px] font-bold text-canvas-muted">{label}</span>
      {[1, 2, 3, 4, 5].map((v) => (
        <button key={v} type="button" role="radio" aria-checked={value === v} disabled={disabled} onClick={() => onPick(v)}
          className={`h-11 w-11 rounded-xl font-mono text-[13px] font-bold transition-transform duration-150 ease-out active:scale-[0.95] disabled:active:scale-100 sm:h-9 sm:w-9 ${value === v ? 'bg-canvas-violet text-white' : 'bg-slate-100'} ${disabled && value !== v ? 'opacity-50' : ''}`}>
          {v}
        </button>
      ))}
    </div>
  );
}

function NoteField({ label, value, disabled, onChange, rewriteId }: { label: string; value: string; disabled: boolean; onChange: (v: string) => void; rewriteId?: string }) {
  const [hint, setHint] = useState<string | null>(null);
  const rw = useMutation({
    mutationFn: () => perfApi.rewrite(rewriteId as string, value),
    onSuccess: (x) => setHint(x.text),
    onError: (e) => toast.error(errText(e, 'Zeki AI yeniden yazamadı.')),
  });
  return (
    <label className="flex flex-col gap-1">
      <span className="flex items-center justify-between gap-2">
        <span className={labelCls}>{label}</span>
        {rewriteId && !disabled && value.trim() && (
          <button type="button" className="inline-flex min-h-9 items-center gap-1 text-[11.5px] font-bold text-canvas-violet hover:underline" disabled={rw.isPending} onClick={() => rw.mutate()}>
            <Sparkles aria-hidden className="h-3.5 w-3.5" />{rw.isPending ? 'Yazıyor…' : 'Zeki AI ile somutlaştır'}
          </button>
        )}
      </span>
      <textarea className={`${field} min-h-[90px]`} value={value} disabled={disabled} onChange={(e) => onChange(e.target.value)} />
      {hint !== null && (
        <div className="rounded-xl bg-canvas-violet/5 p-2.5 text-[12.5px]">
          <div className="whitespace-pre-wrap break-words">{hint}</div>
          <div className="mt-1.5 flex justify-end gap-2">
            <button type="button" className={btnGhost} onClick={() => setHint(null)}>Kalsın</button>
            <button type="button" className={btnPrimary} onClick={() => { onChange(hint); setHint(null); }}>Bunu kullan</button>
          </div>
          <div className="mt-1 text-[11px] text-canvas-muted">Adlar ve iletişim bilgileri Zeki AI'a gönderilmeden gizlendi; yeni olay eklenmez.</div>
        </div>
      )}
    </label>
  );
}

function FlowBox({ r, onChange }: { r: Review; onChange: (x: Review) => void }) {
  const [meeting, setMeeting] = useState('');
  const [comment, setComment] = useState('');
  const [objection, setObjection] = useState(false);
  const [note, setNote] = useState('');
  const act = useMutation({
    mutationFn: (a: 'share' | 'comment' | 'approve') => perfApi.reviewAction(r.id, a,
      a === 'share' ? { meetingAt: meeting ? new Date(meeting).toISOString() : null } : a === 'comment' ? { comment, objection } : { note }),
    onSuccess: (x) => { toast.success(x.stateLabel); onChange(x); },
    onError: (e) => toast.error(errText(e, 'İşlem yapılamadı.')),
  });
  return (
    <Block title="Süreç">
      <ol className="flex flex-col gap-1 text-[12.5px]">
        <li>Öz değerlendirme: {r.selfSubmittedAt ? fmtDateTime(r.selfSubmittedAt) : 'bekleniyor'}</li>
        <li>Yönetici değerlendirmesi: {r.managerSubmittedAt ? fmtDateTime(r.managerSubmittedAt) : 'bekleniyor'}</li>
        <li>Görüşme ve paylaşım: {r.sharedAt ? `${fmtDateTime(r.sharedAt)}${r.meetingAt ? ` · görüşme ${fmtDateTime(r.meetingAt)}` : ''}` : 'bekleniyor'}</li>
        <li>Çalışan yorumu: {r.commentedAt ? `${fmtDateTime(r.commentedAt)}${r.objection ? ' · itiraz' : ''}` : 'bekleniyor'}</li>
        <li>İK onayı: {r.hrApprovedAt ? `${fmtDateTime(r.hrApprovedAt)} · ${r.hrApprovedBy}` : 'bekleniyor'}</li>
      </ol>
      {r.employeeComment && <div className="mt-2 rounded-xl bg-slate-50 p-2.5 text-[12.5px]"><div className={labelCls}>Çalışanın yorumu</div><div className="whitespace-pre-wrap break-words">{r.employeeComment}</div></div>}
      {r.hrNote && <div className="mt-2 text-[12.5px] text-canvas-muted">İK notu: {r.hrNote}</div>}
      {r.can.share && (
        <div className="mt-2 flex flex-wrap items-end gap-2">
          <label className="flex flex-col gap-1"><span className={labelCls}>Görüşme tarihi</span><input type="datetime-local" className={field} value={meeting} onChange={(e) => setMeeting(e.target.value)} /></label>
          <button type="button" className={btnPrimary} disabled={act.isPending} onClick={() => act.mutate('share')}>Çalışanla paylaş</button>
        </div>
      )}
      {r.can.comment && (
        <div className="mt-2 flex flex-col gap-2">
          <textarea className={`${field} min-h-[90px]`} value={comment} onChange={(e) => setComment(e.target.value)} placeholder="Yorumunuz (isteğe bağlı; itirazda zorunlu)" />
          <label className="flex min-h-11 items-center gap-2 text-[12.5px] font-bold"><input type="checkbox" checked={objection} onChange={(e) => setObjection(e.target.checked)} />Bu değerlendirmeye itiraz ediyorum</label>
          <div className="flex justify-end"><button type="button" className={btnPrimary} disabled={act.isPending || (objection && !comment.trim())} onClick={() => act.mutate('comment')}>Gönder</button></div>
        </div>
      )}
      {r.can.approve && (
        <div className="mt-2 flex flex-wrap items-end gap-2">
          <input className={`${field} min-w-0 flex-1`} value={note} onChange={(e) => setNote(e.target.value)} placeholder="İK notu (isteğe bağlı)" />
          <button type="button" className={btnPrimary} disabled={act.isPending} onClick={() => act.mutate('approve')}>Onayla</button>
        </div>
      )}
    </Block>
  );
}

function WorkBox({ r, onChange }: { r: Review; onChange: (x: Review) => void }) {
  const qc = useQueryClient();
  const gen = useMutation({
    mutationFn: () => perfApi.workSummary(r.id),
    onSuccess: () => { toast.success('Özet hazırlandı; çalışan da kendi ekranında görür.'); void perfApi.review(r.id).then(onChange); void qc.invalidateQueries({ queryKey: ['hr', 'perf'] }); },
    onError: (e) => toast.error(errText(e, 'Özet hazırlanamadı.')),
  });
  return (
    <Block title="İş kayıtları özeti" help="Portal görevleri ve CRM sahiplik kayıtlarının sayıları; bilgi amaçlıdır, puan değildir. Portal kullanım kayıtları kullanılmaz."
      action={r.can.workSummary ? <button type="button" className={btnGhost} disabled={gen.isPending} onClick={() => gen.mutate()}>{gen.isPending ? 'Hazırlanıyor…' : 'Özet hazırla'}</button> : undefined}>
      {!r.workSummaries.length && <div className="text-[12px] text-canvas-muted">Özet yok.</div>}
      <ul className="flex flex-col gap-1.5">
        {r.workSummaries.map((w) => (
          <li key={w.id} className="rounded-xl bg-white/80 px-3 py-2 text-[12.5px]">
            <div className="text-[11.5px] text-canvas-muted">{fmtDateTime(w.generatedAt)} · {w.generatedBy}{w.shownToEmployeeAt ? ' · çalışan gördü' : ''}</div>
            <div className="break-words">{w.text}</div>
          </li>
        ))}
      </ul>
    </Block>
  );
}
