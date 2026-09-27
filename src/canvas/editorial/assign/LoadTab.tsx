import { useEffect, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { CalendarX2, ChevronDown, Trash2 } from 'lucide-react';
import { assignApi, type AssignEditor, type EditorAbsence, type EditorTask } from '../../engine';
import { useCan } from '../../useAdmin';
import { Note, Pill, btnGhost, btnPrimary, errText, field, label, nf } from '../../admin/ui';
import { Panel } from '../kit';
import { assignEditorsOptions, assignKeys } from '../queries';
import { LoadMeter, Sheet, StatusPill, TaskEditor, day, todayIso } from './parts';

/** Editör başına iş yükü: ZEKİ AI'daki açık görevler / kapasite, CRM'de iş durumundaki projeler, izinler. */

function TaskRow({ t, editable }: { t: EditorTask; editable: boolean }) {
  const [open, setOpen] = useState(false);
  return (
    <li className="rounded-2xl border border-slate-100 bg-white p-3 text-[12.5px]">
      <button type="button" className="flex w-full items-start justify-between gap-2 text-left" onClick={() => setOpen((v) => !v)} aria-expanded={open} disabled={!editable}>
        <span className="min-w-0">
          <span className="block break-words font-extrabold leading-snug">{t.projectName || 'Adsız proje'}</span>
          <span className={`mt-0.5 block text-[11.5px] ${t.overdue ? 'font-bold text-red-600' : 'text-canvas-muted'}`}>
            {t.roleLabel} · termin {day(t.due)}
            {t.overdue ? ' · gecikmiş' : ''}
            {t.pages ? ` · ${nf.format(t.pages)} sayfa` : ''}
          </span>
        </span>
        <span className="flex shrink-0 items-center gap-1">
          <StatusPill status={t.status} />
          {editable && <ChevronDown aria-hidden className={`h-4 w-4 transition-transform duration-150 ease-out ${open ? 'rotate-180' : ''}`} />}
        </span>
      </button>
      {open && (
        <div className="mt-3 border-t border-slate-100 pt-3">
          <TaskEditor task={t} onDone={() => setOpen(false)} />
        </div>
      )}
    </li>
  );
}

/** İzin ve müsait olmadığı günler: liste, ekleme, silme. Takvimde açık görevle kesişirse çakışma sayılır. */
export function LeaveEditor({ editorId, absences, canEdit }: { editorId: string; absences: EditorAbsence[]; canEdit: boolean }) {
  const qc = useQueryClient();
  const [aStart, setAStart] = useState(todayIso());
  const [aEnd, setAEnd] = useState(todayIso());
  const [aReason, setAReason] = useState('');
  const refresh = () => qc.invalidateQueries({ queryKey: assignKeys.all });
  const addLeave = useMutation({
    mutationFn: () => assignApi.addAbsence(editorId, { start: aStart, end: aEnd, reason: aReason.trim() || undefined }),
    onSuccess: () => {
      refresh();
      setAReason('');
    },
  });
  const delLeave = useMutation({ mutationFn: (id: string) => assignApi.deleteAbsence(id), onSuccess: refresh });
  return (
    <section>
      <h3 className="text-[13px] font-extrabold">İzin ve müsait olmadığı günler</h3>
      <ul className="mt-2 space-y-1.5">
        {absences.map((a) => (
          <li key={a.id} className="flex items-center justify-between gap-2 rounded-xl bg-slate-50 px-3 py-2 text-[12px]">
            <span className="flex min-w-0 items-center gap-1.5">
              <CalendarX2 aria-hidden className="h-3.5 w-3.5 shrink-0 text-canvas-muted" />
              <span className="min-w-0 break-words">
                {day(a.start)} – {day(a.end)}
                {a.reason ? ` · ${a.reason}` : ''}
              </span>
            </span>
            {canEdit && (
              <button type="button" aria-label="İzni sil" className="flex h-11 w-11 shrink-0 items-center justify-center rounded-lg text-canvas-muted hover:bg-white sm:h-8 sm:w-8" onClick={() => delLeave.mutate(a.id)} disabled={delLeave.isPending}>
                <Trash2 aria-hidden className="h-4 w-4" />
              </button>
            )}
          </li>
        ))}
        {!absences.length && <li className="text-[12px] text-canvas-muted">Bugünden sonra kayıtlı izin yok.</li>}
      </ul>
      {canEdit && (
        <form
          className="mt-2 grid grid-cols-2 gap-2 sm:grid-cols-[1fr_1fr_1.4fr_auto] sm:items-end"
          onSubmit={(e) => {
            e.preventDefault();
            if (aEnd >= aStart) addLeave.mutate();
          }}
        >
          <label className="block">
            <span className={label}>Başlangıç</span>
            <input type="date" value={aStart} onChange={(e) => setAStart(e.target.value)} className={`${field} mt-1`} required />
          </label>
          <label className="block">
            <span className={label}>Bitiş</span>
            <input type="date" value={aEnd} min={aStart} onChange={(e) => setAEnd(e.target.value)} className={`${field} mt-1`} required />
          </label>
          <label className="col-span-2 block sm:col-span-1">
            <span className={label}>Neden</span>
            <input value={aReason} onChange={(e) => setAReason(e.target.value)} placeholder="Yıllık izin, fuar…" className={`${field} mt-1`} />
          </label>
          <button type="submit" className={`${btnGhost} col-span-2 sm:col-span-1`} disabled={addLeave.isPending || aEnd < aStart}>
            Ekle
          </button>
        </form>
      )}
      {(addLeave.error || delLeave.error) && <Note tone="err">{errText(addLeave.error || delLeave.error, 'İzin kaydedilemedi.')}</Note>}
    </section>
  );
}

function EditorSheet({ editor, isMe, onClose }: { editor: AssignEditor | null; isMe: boolean; onClose: () => void }) {
  const qc = useQueryClient();
  const canAssign = useCan('editor-atama.ata');
  const [capacity, setCapacity] = useState('');
  const [available, setAvailable] = useState(true);
  const [note, setNote] = useState('');
  useEffect(() => {
    if (!editor) return;
    setCapacity(editor.profile?.capacity != null ? String(editor.profile.capacity) : '');
    setAvailable(editor.profile?.available ?? true);
    setNote(editor.profile?.note ?? '');
    // Aynı kişi tazelenince (izin eklendi) yazılmakta olan profil silinmesin; kişi ya da kayıt değişince sıfırlanır.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [editor?.id, editor?.profile?.updatedAt]);
  const refresh = () => qc.invalidateQueries({ queryKey: assignKeys.all });
  const profile = useMutation({
    mutationFn: () => assignApi.saveProfile(editor!.id, { capacity: capacity ? Number(capacity) : null, available, note: note.trim() || null }),
    onSuccess: () => {
      refresh();
      toast.success('Profil kaydedildi');
    },
  });
  const canLeave = canAssign || isMe;

  return (
    <Sheet
      open={!!editor}
      onOpenChange={(o) => !o && onClose()}
      title={editor?.name || 'Editör'}
      sub={editor ? `${nf.format(editor.crmOpen)} projede CRM editörü (iş planı / kurul onaylı) · dönemde toplam ${nf.format(editor.crmTotal)} proje` : undefined}
    >
      {editor && (
        <div className="space-y-5">
          <LoadMeter load={editor.load} />

          <section>
            <h3 className="text-[13px] font-extrabold">Kapasite ve atama</h3>
            {canAssign ? (
              <form
                className="mt-2 space-y-2"
                onSubmit={(e) => {
                  e.preventDefault();
                  profile.mutate();
                }}
              >
                <div className="grid grid-cols-2 gap-2">
                  <label className="block">
                    <span className={label}>Eşzamanlı görev kapasitesi</span>
                    <input inputMode="numeric" pattern="[0-9]*" value={capacity} onChange={(e) => setCapacity(e.target.value.replace(/\D/g, ''))} placeholder="Girilmemiş" className={`${field} mt-1`} />
                  </label>
                  <label className="flex min-h-11 items-center gap-2 self-end rounded-xl border border-slate-200 bg-white px-3 text-[12.5px] font-bold">
                    <input type="checkbox" checked={available} onChange={(e) => setAvailable(e.target.checked)} className="h-4 w-4 accent-canvas-violet" />
                    Atamaya açık
                  </label>
                </div>
                <label className="block">
                  <span className={label}>Not</span>
                  <input value={note} onChange={(e) => setNote(e.target.value)} placeholder="Ör. yalnız çocuk kitapları" className={`${field} mt-1`} />
                </label>
                {profile.error && <Note tone="err">{errText(profile.error, 'Profil kaydedilemedi.')}</Note>}
                <div className="flex justify-end">
                  <button type="submit" className={btnPrimary} disabled={profile.isPending}>
                    {profile.isPending ? 'Kaydediliyor…' : 'Profili kaydet'}
                  </button>
                </div>
              </form>
            ) : (
              <p className="mt-1 text-[12px] text-canvas-muted">
                Kapasite: {editor.profile?.capacity != null ? nf.format(editor.profile.capacity) : 'girilmemiş'} ·{' '}
                {editor.profile?.available === false ? 'atamaya kapalı' : 'atamaya açık'}
                {editor.profile?.note ? ` · ${editor.profile.note}` : ''}
              </p>
            )}
          </section>

          <LeaveEditor editorId={editor.id} absences={editor.absences} canEdit={canLeave} />

          <section>
            <h3 className="text-[13px] font-extrabold">Açık görevler ({nf.format(editor.tasks.length)})</h3>
            {!editor.tasks.length && <p className="mt-1 text-[12px] text-canvas-muted">ZEKİ AI'da açık görevi yok.</p>}
            <ul className="mt-2 space-y-1.5">
              {editor.tasks.map((t) => (
                <TaskRow key={t.id} t={t} editable={canAssign || isMe} />
              ))}
            </ul>
          </section>
        </div>
      )}
    </Sheet>
  );
}

export default function LoadTab() {
  const q = useQuery(assignEditorsOptions());
  const [openId, setOpenId] = useState('');
  const [showClosed, setShowClosed] = useState(false);
  const items = q.data?.items ?? [];
  const current = items.find((e) => e.id === openId) ?? null;
  const shown = showClosed ? items : items.filter((e) => !e.disabled);
  const closed = items.length - items.filter((e) => !e.disabled).length;
  const err = errText(q.error, 'Editörler okunamadı.');

  return (
    <Panel>
      <div className="flex flex-wrap items-baseline justify-between gap-2 px-1">
        <h2 className="text-[13px] font-extrabold">İş yükü</h2>
        {closed > 0 && (
          <label className="flex min-h-9 items-center gap-1.5 text-[11.5px] font-bold text-canvas-muted">
            <input type="checkbox" checked={showClosed} onChange={(e) => setShowClosed(e.target.checked)} className="h-4 w-4 accent-canvas-violet" />
            CRM hesabı kapalı {nf.format(closed)} kişiyi göster
          </label>
        )}
      </div>
      <p className="mt-0.5 px-1 text-[11.5px] leading-snug text-canvas-muted">
        Yük, ZEKİ AI'daki açık görevlerin editörün kapasitesine oranıdır. «CRM» sayısı, CRM'de editörü olduğu iş planı / kurul onaylı projelerdir; CRM'de bu durumlar kitap basıldıktan sonra da kapanmadığı için yüke katılmaz.
      </p>
      {err && <Note tone="err">{err}</Note>}
      {q.isLoading && <p className="py-10 text-center text-[12.5px] text-canvas-muted">Editörler okunuyor…</p>}
      <ul className="mt-3 grid gap-2 sm:grid-cols-2 xl:grid-cols-3">
        {shown.map((e) => (
          <li key={e.id}>
            <button
              type="button"
              onClick={() => setOpenId(e.id)}
              className="h-full w-full rounded-2xl border border-slate-100 bg-white/85 p-3 text-left text-[12.5px] transition-transform duration-150 ease-out active:scale-[0.98]"
            >
              <span className="flex flex-wrap items-center gap-1.5">
                <span className="break-words font-extrabold">{e.name || 'Adı kayıtlı değil'}</span>
                {q.data?.me?.id === e.id && <Pill tone="violet">Siz</Pill>}
                {e.disabled && <Pill tone="muted">CRM hesabı kapalı</Pill>}
                {e.profile?.available === false && <Pill tone="warn">Atamaya kapalı</Pill>}
              </span>
              <span className="mt-2 block">
                <LoadMeter load={e.load} />
              </span>
              <span className="mt-1.5 flex flex-wrap gap-x-3 text-[11px] text-canvas-muted">
                <span>CRM {nf.format(e.crmOpen)}</span>
                {e.absences.length > 0 && (
                  <span className="font-bold text-amber-700">
                    İzin {day(e.absences[0].start)}
                    {e.absences.length > 1 ? ` +${e.absences.length - 1}` : ''}
                  </span>
                )}
              </span>
            </button>
          </li>
        ))}
      </ul>
      <EditorSheet editor={current} isMe={!!current && q.data?.me?.id === current.id} onClose={() => setOpenId('')} />
    </Panel>
  );
}
