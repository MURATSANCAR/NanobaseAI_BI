import { useEffect, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Check, Loader2 } from 'lucide-react';
import { assignApi, type AssignCandidate, type AssignProject } from '../../engine';
import { Note, Pill, btnGhost, btnPrimary, errText, field, label, nf } from '../../admin/ui';
import { crmLabel } from '../../format';
import { useDebounced } from '../kit';
import { assignKeys, assignSuggestOptions } from '../queries';
import { ConflictList, LoadMeter, Sheet, addDays, day, projectMeta, todayIso } from './parts';
import SqlInfo from '../../components/SqlInfo';
import { kaynakOf } from '../../components/kaynakOf';

/** Projeye editör atama: tarih aralığına göre adaylar (kural, geçmiş, yük, takvim) ve atama formu. */

function Candidate({ c, picked, onPick }: { c: AssignCandidate; picked: boolean; onPick: () => void }) {
  return (
    <li>
      <button
        type="button"
        onClick={onPick}
        aria-pressed={picked}
        className={`w-full rounded-2xl border p-3 text-left text-[12.5px] transition-transform duration-150 ease-out active:scale-[0.98] ${picked ? 'border-canvas-violet bg-canvas-violet/5 ring-1 ring-canvas-violet' : 'border-slate-100 bg-white'}`}
      >
        <span className="flex items-start justify-between gap-2">
          <span className="min-w-0">
            <span className="flex flex-wrap items-center gap-1.5">
              <span className="break-words font-extrabold">{c.name || 'Adı kayıtlı değil'}</span>
              {c.rule && <Pill tone="violet">Kural · {c.rule}</Pill>}
              {c.conflicts.length > 0 && <Pill tone="warn">Çakışma</Pill>}
            </span>
            <span className="mt-0.5 block text-[11.5px] leading-snug text-canvas-muted">{c.reasons.join(' · ')}</span>
          </span>
          <span className="flex shrink-0 items-center gap-1.5">
            <span className="font-mono text-[15px] font-bold tabular-nums" title="Öneri puanı">
              {nf.format(Math.round(c.score))}
            </span>
            {picked && <Check aria-hidden className="h-4 w-4 text-canvas-violet" />}
          </span>
        </span>
        <span className="mt-2 block">
          <LoadMeter load={c.load} compact />
        </span>
        <ConflictList items={c.conflicts} />
      </button>
    </li>
  );
}

export default function AssignSheet({ project, onClose, canAssign }: { project: AssignProject | null; onClose: () => void; canAssign: boolean }) {
  const qc = useQueryClient();
  const open = !!project;
  const [start, setStart] = useState(todayIso());
  const [due, setDue] = useState('');
  const [editor, setEditor] = useState('');
  const [role, setRole] = useState<'editor' | 'destek'>('editor');
  const [pages, setPages] = useState('');
  const [note, setNote] = useState('');
  const [showAll, setShowAll] = useState(false);

  useEffect(() => {
    if (!project) return;
    setStart(todayIso());
    setDue(project.targetPrint && project.targetPrint > todayIso() ? project.targetPrint : '');
    setEditor('');
    setRole('editor');
    setPages(project.pages ? String(project.pages) : '');
    setNote('');
    setShowAll(false);
  }, [project]);

  const winStart = useDebounced(start, 300);
  const winDue = useDebounced(due, 300);
  const sugg = useQuery(assignSuggestOptions(project?.id ?? '', winStart, winDue));
  const data = sugg.data?.project.id === project?.id ? sugg.data : undefined;
  const items = data?.items ?? [];
  const picked = items.find((c) => c.id === editor);
  const hasEditorTask = (data?.tasks ?? []).some((t) => t.role === 'editor' && ['sirada', 'calisiyor', 'beklemede'].includes(t.status));
  useEffect(() => {
    if (hasEditorTask) setRole('destek');
  }, [hasEditorTask]);

  const save = useMutation({
    mutationFn: (force: boolean) =>
      assignApi.assign({
        projectId: project!.id,
        editorId: editor,
        role,
        start,
        due,
        pages: pages ? Number(pages) : null,
        note: note.trim() || undefined,
        force,
      }),
    onSuccess: (t) => {
      qc.invalidateQueries({ queryKey: assignKeys.all });
      qc.invalidateQueries({ queryKey: ['editorial', 'projects'] });
      toast.success(`${t.editorName ?? 'Editör'} atandı`, { description: `${t.projectName ?? ''} · termin ${day(t.due)}` });
      onClose();
    },
  });
  const err = errText(save.error, 'Atama yapılamadı.');
  const bad = !!(due && due < start);
  const ready = !!editor && !!due && !bad;
  const conflicted = !!picked?.conflicts.length;
  const shown = showAll ? items : items.slice(0, 6);

  return (
    <Sheet
      open={open}
      onOpenChange={(o) => !o && onClose()}
      title={project?.name || 'Adsız proje'}
      sub={project ? projectMeta(project) : undefined}
    >
      {project && (
        <form
          className="space-y-4"
          onSubmit={(e) => {
            e.preventDefault();
            if (ready && canAssign) save.mutate(false);
          }}
        >
          <div className="flex flex-wrap items-center gap-1.5 text-[11.5px]">
            {project.status && <Pill tone="muted">{crmLabel(project.status)}</Pill>}
            {data?.categoryLabel && <Pill tone="violet">{data.categoryLabel}</Pill>}
            {data && (data.rule ? <span className="text-canvas-muted">Kural sürümü {data.ruleVersion}</span> : <span className="text-canvas-muted">Bu kategoride yürürlükte kural yok</span>)}
          </div>
          {(data?.tasks ?? []).length > 0 && (
            <Note tone="info">
              Bu projedeki görevler:{' '}
              {data!.tasks.map((t) => `${t.editorName} (${t.roleLabel}, ${t.statusLabel.toLocaleLowerCase('tr')})`).join(' · ')}
            </Note>
          )}

          <div className="grid grid-cols-2 gap-2">
            <label className="block">
              <span className={label}>Başlangıç</span>
              <input type="date" value={start} onChange={(e) => setStart(e.target.value)} className={`${field} mt-1`} required />
            </label>
            <label className="block">
              <span className={label}>Termin</span>
              <input type="date" value={due} min={start} onChange={(e) => setDue(e.target.value)} className={`${field} mt-1`} required />
            </label>
          </div>
          <div className="flex flex-wrap gap-1.5">
            {[30, 60, 90].map((n) => (
              <button key={n} type="button" className={`${btnGhost} min-h-9 px-2.5 py-1 text-[11.5px]`} onClick={() => setDue(addDays(start || todayIso(), n))}>
                +{n} gün
              </button>
            ))}
          </div>
          {bad && <Note tone="err">Termin, başlangıçtan önce olamaz.</Note>}
          {!due && <p className="text-[11.5px] text-canvas-muted">Termin girilince adayların takvim çakışması bu aralığa göre hesaplanır.</p>}

          <section>
            <div className="flex items-baseline justify-between gap-2">
              <h3 className="flex items-center gap-1 text-[13px] font-extrabold">
                Adaylar
                <SqlInfo k={kaynakOf(data)} alan="_hepsi" label="Aday uygunluğu ve yük" />
              </h3>
              {sugg.isFetching && <Loader2 aria-hidden className="h-3.5 w-3.5 animate-spin text-canvas-muted" />}
            </div>
            <p className="mt-0.5 text-[11.5px] leading-snug text-canvas-muted">
              Puan: kural (birincil 40, yedek 20) + bu kategorideki geçmiş (en çok 30) + boş kapasite (en çok 20; kapasite girilmemişse 10) − çakışma başına 25.
            </p>
            {sugg.isLoading && <p className="py-6 text-center text-[12px] text-canvas-muted">Adaylar hesaplanıyor…</p>}
            {sugg.error && <Note tone="err">{errText(sugg.error, 'Adaylar okunamadı.')}</Note>}
            <ul className="mt-2 space-y-1.5">
              {shown.map((c) => (
                <Candidate key={c.id} c={c} picked={editor === c.id} onPick={() => canAssign && setEditor(editor === c.id ? '' : c.id)} />
              ))}
            </ul>
            {items.length > 6 && (
              <button type="button" className={`${btnGhost} mt-2 w-full`} onClick={() => setShowAll((v) => !v)} aria-expanded={showAll}>
                {showAll ? 'Yalnız ilk altıyı göster' : `Bütün adaylar (${nf.format(items.length)})`}
              </button>
            )}
            {(data?.excluded ?? []).length > 0 && (
              <details className="mt-2 text-[11.5px] text-canvas-muted">
                <summary className="cursor-pointer font-bold">Atanamayanlar ({nf.format(data!.excluded.length)})</summary>
                <ul className="mt-1 space-y-0.5">
                  {data!.excluded.map((x) => (
                    <li key={x.id}>
                      {x.name} — {x.reason}
                    </li>
                  ))}
                </ul>
              </details>
            )}
          </section>

          {canAssign ? (
            <>
          <div className="grid grid-cols-2 gap-2">
            <label className="block">
              <span className={label}>Rol</span>
              <select value={role} onChange={(e) => setRole(e.target.value as 'editor' | 'destek')} className={`${field} mt-1`}>
                <option value="editor" disabled={hasEditorTask}>
                  Editör
                </option>
                <option value="destek">Destek editör</option>
              </select>
            </label>
            <label className="block">
              <span className={label}>Tahmini sayfa</span>
              <input inputMode="numeric" pattern="[0-9]*" value={pages} onChange={(e) => setPages(e.target.value.replace(/\D/g, ''))} className={`${field} mt-1`} />
            </label>
          </div>
          <label className="block">
            <span className={label}>Not (editör görür)</span>
            <textarea value={note} onChange={(e) => setNote(e.target.value)} rows={2} className={`${field} mt-1 resize-y`} />
          </label>

          {project.crmEditor && <Note tone="info">CRM'de yazan editör: {project.crmEditor}. Atama CRM'e yazılmaz; CRM kartını ayrıca güncelleyin.</Note>}
          {!project.crmEditor && <Note tone="info">Atama ZEKİ AI'da kaydedilir, CRM'e yazılmaz. CRM proje kartındaki «Editörü» alanını ayrıca güncelleyin.</Note>}
          {conflicted && (
            <Note tone="warn">
              {picked!.name} için bu aralıkta çakışma var. Yine de atarsanız çakışma görev geçmişine yazılır.
            </Note>
          )}
          {err && <Note tone="err">{err}</Note>}

          <div className="sticky bottom-0 -mx-1 flex flex-wrap justify-end gap-2 bg-white px-1 pb-1 pt-2">
            <button type="button" className={btnGhost} onClick={onClose}>
              Vazgeç
            </button>
            {conflicted ? (
              <button type="button" className={btnPrimary} disabled={!ready || save.isPending} onClick={() => save.mutate(true)}>
                {save.isPending ? 'Atanıyor…' : 'Çakışmaya rağmen ata'}
              </button>
            ) : (
              <button type="submit" className={btnPrimary} disabled={!ready || save.isPending}>
                {save.isPending ? 'Atanıyor…' : picked ? `Ata: ${picked.name}` : 'Aday seçin'}
              </button>
            )}
          </div>
            </>
          ) : (
            <Note tone="info">Atama yetkiniz yok; adayları ve gerekçelerini görebilirsiniz.</Note>
          )}
        </form>
      )}
    </Sheet>
  );
}

