import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { ArrowRight, Check, Inbox } from 'lucide-react';
import { ENGINE_ENABLED, assignApi, type EditorTask, type TaskStatus } from '../engine';
import { Note, Pill, errText, nf } from '../admin/ui';
import { crmLabel } from '../format';
import { Kpi, KpiRow, ModuleFrame, Panel } from './kit';
import { assignKeys, myTasksOptions } from './queries';
import { LeaveEditor } from './assign/LoadTab';
import { LoadMeter, STATUS_LABEL, STATUS_ORDER, Sheet, TaskEditor, day, daysBetween, projectMeta, todayIso } from './assign/parts';

/** M2 editörün kendi görev panosu. Görevler ZEKİ AI'daki atamalardır; CRM'de editörü olduğu ama panoda
 *  olmayan iş durumundaki projeler ayrı listelenir ve «Panoma al» ile panoya girer. Durum, termin ve not
 *  buradan güncellenir; termin değişikliği gerekçe ister ve atayan görür. */

const NEXT: Partial<Record<TaskStatus, { to: TaskStatus; label: string }>> = {
  sirada: { to: 'calisiyor', label: 'Başladım' },
  calisiyor: { to: 'tamamlandi', label: 'Tamamladım' },
  beklemede: { to: 'calisiyor', label: 'Devam ediyorum' },
};

function dueText(t: EditorTask): { text: string; tone: string } {
  if (!t.due) return { text: 'Termin girilmemiş', tone: 'text-canvas-muted' };
  if (t.status === 'tamamlandi') return { text: `Termin ${day(t.due)}`, tone: 'text-canvas-muted' };
  const left = daysBetween(todayIso(), t.due);
  if (left < 0) return { text: `${nf.format(-left)} gün gecikti · ${day(t.due)}`, tone: 'font-bold text-red-600' };
  if (left === 0) return { text: `Termin bugün`, tone: 'font-bold text-amber-700' };
  return { text: `${nf.format(left)} gün kaldı · ${day(t.due)}`, tone: left <= 7 ? 'font-bold text-amber-700' : 'text-canvas-muted' };
}

function TaskCard({ t, onOpen }: { t: EditorTask; onOpen: () => void }) {
  const qc = useQueryClient();
  const next = NEXT[t.status];
  const move = useMutation({
    mutationFn: (to: TaskStatus) => assignApi.updateTask(t.id, { status: to }),
    onSuccess: (x) => {
      qc.invalidateQueries({ queryKey: assignKeys.all });
      toast.success(`${x.projectName ?? 'Görev'}: ${STATUS_LABEL[x.status]}`);
    },
    onError: (e) => toast.error(errText(e, 'Görev güncellenemedi.') ?? ''),
  });
  const due = dueText(t);
  return (
    <li className="rounded-2xl border border-slate-100 bg-white p-3 text-[12.5px] shadow-sm">
      <button type="button" onClick={onOpen} className="block w-full text-left">
        <span className="flex items-start justify-between gap-2">
          <span className="break-words font-extrabold leading-snug">{t.projectName || 'Adsız proje'}</span>
          {t.role === 'destek' && <Pill tone="muted">Destek</Pill>}
        </span>
        {t.category && <span className="mt-0.5 block text-[11px] text-canvas-muted">{t.category}</span>}
        <span className={`mt-1 block text-[11.5px] ${due.tone}`}>{due.text}</span>
        {(t.pages || t.note) && (
          <span className="mt-0.5 block text-[11px] leading-snug text-canvas-muted">
            {[t.pages ? `${nf.format(t.pages)} sayfa` : null, t.note].filter(Boolean).join(' · ')}
          </span>
        )}
      </button>
      {next && (
        <button
          type="button"
          onClick={() => move.mutate(next.to)}
          disabled={move.isPending}
          className="mt-2 inline-flex min-h-11 w-full items-center justify-center gap-1.5 rounded-xl bg-slate-100 px-3 text-[12px] font-extrabold transition-transform duration-150 ease-out hover:bg-slate-200 active:scale-[0.97] disabled:opacity-50 sm:min-h-9"
        >
          {next.to === 'tamamlandi' ? <Check aria-hidden className="h-4 w-4" /> : <ArrowRight aria-hidden className="h-4 w-4" />}
          {next.label}
        </button>
      )}
    </li>
  );
}

export default function MyTasksScreen() {
  const qc = useQueryClient();
  const q = useQuery(myTasksOptions());
  const d = q.data;
  const [col, setCol] = useState<TaskStatus>('sirada');
  const [openId, setOpenId] = useState('');
  const tasks = d?.tasks ?? [];
  const byStatus = (s: TaskStatus) => tasks.filter((t) => t.status === s);
  const current = tasks.find((t) => t.id === openId) ?? null;
  const adopt = useMutation({
    mutationFn: assignApi.adopt,
    onSuccess: (t) => {
      qc.invalidateQueries({ queryKey: assignKeys.all });
      toast.success('Panoya alındı', { description: `${t.projectName ?? ''} · termin girin` });
      setOpenId(t.id);
    },
    onError: (e) => toast.error(errText(e, 'Panoya alınamadı.') ?? ''),
  });
  const open = tasks.filter((t) => t.status !== 'tamamlandi' && t.status !== 'iptal');
  const overdue = open.filter((t) => t.overdue).length;
  const week = open.filter((t) => t.due && !t.overdue && daysBetween(todayIso(), t.due) <= 7).length;
  const err = errText(q.error, 'Görevler okunamadı.');

  return (
    <ModuleFrame
      route="/gorevlerim"
      crumb="Görevlerim"
      title={d?.me?.name ? `${d.me.name} · görevlerim` : 'Görevlerim'}
      lead="Size atanan editörlük işleri. Durumu ve termini buradan güncellersiniz; atayan kişi değişikliği ve gerekçesini görür."
      source="ZEKİ AI atamaları + CRM projeleri"
    >
      {!ENGINE_ENABLED && <Note tone="warn">ZEKİ AI bağlantısı bu derlemede tanımlı değil.</Note>}
      {err && <Note tone="err">{err}</Note>}
      {q.isLoading && <Panel><p className="py-10 text-center text-[12.5px] text-canvas-muted">Görevler okunuyor…</p></Panel>}
      {d && !d.me && (
        <Panel>
          <div className="flex flex-col items-center gap-2 py-8 text-center">
            <Inbox aria-hidden className="h-8 w-8 text-canvas-muted" />
            <p className="max-w-[52ch] text-[12.5px] text-canvas-muted">
              «{d.user}» hesabının CRM'de kullanıcı kaydı bulunamadı. Görev panosu CRM kullanıcısına bağlıdır; CRM'deki kullanıcı kartınızın etki alanı adı AD hesabınızla aynı olmalı.
            </p>
          </div>
        </Panel>
      )}

      {d?.me && (
        <>
          <KpiRow>
            <Kpi label="Açık görev" value={nf.format(open.length)} help="Sırada, çalışılıyor, beklemede" />
            <Kpi label="Gecikmiş" value={nf.format(overdue)} help="Termini geçmiş açık görev" />
            <Kpi label="Bu hafta" value={nf.format(week)} help="Termini 7 gün içinde" />
            <Kpi label="CRM'de size yazılı" value={nf.format(d.crmOnly.length)} help="İş planı / kurul onaylı, panoda değil" />
          </KpiRow>
          {d.load && (
            <Panel>
              <LoadMeter load={d.load} />
            </Panel>
          )}

          <div role="tablist" aria-label="Pano sütunu" className="-mx-1 flex gap-1 overflow-x-auto px-1 lg:hidden">
            {STATUS_ORDER.map((s) => (
              <button
                key={s}
                type="button"
                role="tab"
                aria-selected={col === s}
                onClick={() => setCol(s)}
                className={`min-h-11 shrink-0 rounded-xl px-3 text-[12.5px] font-extrabold transition-transform duration-150 ease-out active:scale-[0.97] ${col === s ? 'bg-canvas-ink text-white' : 'bg-white/80'}`}
              >
                {STATUS_LABEL[s]} <span className="font-mono tabular-nums">{nf.format(byStatus(s).length)}</span>
              </button>
            ))}
          </div>
          <div className="grid gap-3 lg:grid-cols-4 lg:gap-4">
            {STATUS_ORDER.map((s) => (
              <section key={s} className={`glass-panel rounded-2xl p-3 shadow-glass-float sm:rounded-3xl ${col === s ? '' : 'hidden lg:block'}`} aria-label={STATUS_LABEL[s]}>
                <h2 className="flex items-baseline justify-between px-1 text-[13px] font-extrabold">
                  {STATUS_LABEL[s]}
                  <span className="font-mono text-[12px] tabular-nums text-canvas-muted">{nf.format(byStatus(s).length)}</span>
                </h2>
                {s === 'tamamlandi' && <p className="px-1 text-[11px] text-canvas-muted">Son 30 gün</p>}
                <ul className="mt-2 space-y-2">
                  {byStatus(s).map((t) => (
                    <TaskCard key={t.id} t={t} onOpen={() => setOpenId(t.id)} />
                  ))}
                </ul>
                {!byStatus(s).length && <p className="py-6 text-center text-[12px] text-canvas-muted">Boş</p>}
              </section>
            ))}
          </div>

          {d.crmOnly.length > 0 && (
            <Panel>
              <h2 className="px-1 text-[13px] font-extrabold">CRM'de size yazılı, panoda olmayan projeler ({nf.format(d.crmOnly.length)})</h2>
              <p className="mt-0.5 px-1 text-[11.5px] leading-snug text-canvas-muted">
                CRM proje kartında «Editörü» siz olan, iş planı ya da kurul onaylı durumdaki {d.sinceYear} ve sonrası projeler. Çalıştığınız projeyi panoya alın; CRM'de bu durumlar kitap basıldıktan sonra da açık kalabildiği için hepsi iş sayılmaz.
              </p>
              <ul className="mt-3 grid gap-2 md:grid-cols-2">
                {d.crmOnly.map((p) => (
                  <li key={p.id} className="flex flex-col gap-2 rounded-2xl border border-slate-100 bg-white/85 p-3 text-[12.5px] sm:flex-row sm:items-center sm:justify-between">
                    <div className="min-w-0">
                      <div className="break-words font-extrabold leading-snug">{p.name || 'Adsız proje'}</div>
                      <div className="mt-0.5 text-[11.5px] leading-snug text-canvas-muted">
                        {[p.status && crmLabel(p.status), projectMeta(p)].filter(Boolean).join(' · ')}
                      </div>
                    </div>
                    <button
                      type="button"
                      onClick={() => adopt.mutate(p.id)}
                      disabled={adopt.isPending}
                      className="inline-flex min-h-11 shrink-0 items-center justify-center rounded-xl bg-canvas-violet px-3.5 text-[12.5px] font-extrabold text-white shadow-md transition-transform duration-150 ease-out active:scale-[0.97] disabled:opacity-50 sm:min-h-9"
                    >
                      Panoma al
                    </button>
                  </li>
                ))}
              </ul>
            </Panel>
          )}

          <Panel>
            <LeaveEditor editorId={d.me.id} absences={d.absences} canEdit />
          </Panel>
        </>
      )}

      <Sheet
        open={!!current}
        onOpenChange={(o) => !o && setOpenId('')}
        title={current?.projectName || 'Görev'}
        sub={current ? [current.category, current.roleLabel, current.createdBy && `Atayan ${current.createdBy}`].filter(Boolean).join(' · ') : undefined}
      >
        {current && <TaskEditor key={current.id} task={current} onDone={() => setOpenId('')} />}
      </Sheet>
    </ModuleFrame>
  );
}
