import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { ArrowRight, Check } from 'lucide-react';
import { assignApi, type EditorTask, type TaskStatus } from '../engine';
import { Note, Pill, errText, nf } from '../admin/ui';
import { crmLabel } from '../format';
import { Kpi, KpiRow, Panel } from './kit';
import { assignKeys, myTasksOptions } from './queries';
import { STATUS_LABEL, STATUS_ORDER, Sheet, TaskEditor, day, daysBetween, projectMeta, todayIso } from './assign/parts';
import SqlInfo from '../components/SqlInfo';
import { kaynakOf } from '../components/kaynakOf';

/** Masam › Görevlerim (eski «Görevlerim» ekranı, 2026-09-29'da Masam'a taşındı). Liste CRM'den gelir: proje
 *  kartında «Editörü» siz olan iş planı / kurul onaylı projeler. Durum, termin, sayfa ve not sizin takibinizdir;
 *  CRM'e yazılmaz. Termini olan işte termin değişikliği gerekçe ister. */

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
  if (left === 0) return { text: 'Termin bugün', tone: 'font-bold text-amber-700' };
  return { text: `${nf.format(left)} gün kaldı · ${day(t.due)}`, tone: left <= 7 ? 'font-bold text-amber-700' : 'text-canvas-muted' };
}

function TaskCard({ t, onOpen }: { t: EditorTask; onOpen: () => void }) {
  const qc = useQueryClient();
  const next = NEXT[t.status];
  const move = useMutation({
    mutationFn: (to: TaskStatus) => assignApi.updateMine(t.projectId, { status: to }),
    onSuccess: (x) => {
      qc.invalidateQueries({ queryKey: assignKeys.all });
      toast.success(`${x.projectName ?? 'Görev'}: ${STATUS_LABEL[x.status]}`);
    },
    onError: (e) => toast.error(errText(e, 'Görev güncellenemedi.') ?? ''),
  });
  const due = dueText(t);
  const crm = t.project;
  return (
    <li className="rounded-2xl border border-slate-100 bg-white p-3 text-[12.5px] shadow-sm">
      <button type="button" onClick={onOpen} className="block w-full text-left">
        <span className="flex items-start justify-between gap-2">
          <span className="break-words font-extrabold leading-snug">{t.projectName || 'Adsız proje'}</span>
          {t.status === 'iptal' && <Pill tone="muted">İptal</Pill>}
        </span>
        {crm && <span className="mt-0.5 block text-[11px] leading-snug text-canvas-muted">{projectMeta(crm)}</span>}
        {crm?.status && <span className="mt-0.5 block text-[11px] text-canvas-muted">CRM: {crmLabel(crm.status)}</span>}
        <span className={`mt-1 block text-[11.5px] ${due.tone}`}>{due.text}</span>
        {t.note && <span className="mt-0.5 block text-[11px] leading-snug text-canvas-muted">{t.note}</span>}
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

export default function MyTasks() {
  const q = useQuery(myTasksOptions());
  const d = q.data;
  const [col, setCol] = useState<TaskStatus>('sirada');
  const [openId, setOpenId] = useState('');
  const tasks = d?.tasks ?? [];
  // İptal edilen iş «Tamamlandı» sütununda durur (son 30 gün); kartta iptal yazılır, açılıp geri alınabilir.
  const byStatus = (s: TaskStatus) => tasks.filter((t) => t.status === s || (s === 'tamamlandi' && t.status === 'iptal'));
  const current = tasks.find((t) => t.projectId === openId) ?? null;
  const open = tasks.filter((t) => t.status !== 'tamamlandi' && t.status !== 'iptal');
  const overdue = open.filter((t) => t.overdue).length;
  const week = open.filter((t) => t.due && !t.overdue && daysBetween(todayIso(), t.due) <= 7).length;
  const undated = open.filter((t) => !t.due).length;
  const err = errText(q.error, 'Görevler okunamadı.');

  // CRM'de kullanıcı kaydı olmayan kişide (editör değil) bölüm hiç çizilmez.
  if (!err && (!d || !d.me)) return null;

  return (
    <section aria-labelledby="gorevlerim" className="space-y-3">
      <div className="flex flex-wrap items-baseline justify-between gap-2 px-1">
        <h2 id="gorevlerim" className="flex items-center gap-1 text-[13px] font-extrabold">
          Görevlerim
          <SqlInfo k={kaynakOf(d)} alan="_hepsi" label="Görevlerim" />
        </h2>
        <span className="text-[11.5px] text-canvas-muted">CRM'de editörü siz olan {d?.sinceYear ? `${d.sinceYear} ve sonrası ` : ''}iş durumundaki projeler</span>
      </div>
      {err && <Note tone="err">{err}</Note>}
      {d?.me && !tasks.length && (
        <Panel>
          <p className="py-4 text-center text-[12.5px] text-canvas-muted">CRM'de editörü siz olan, iş planı ya da kurul onaylı durumda proje yok.</p>
        </Panel>
      )}
      {d?.me && tasks.length > 0 && (
        <>
          <KpiRow>
            <Kpi label="Açık görev" value={nf.format(open.length)} help="Sırada, çalışılıyor, beklemede" />
            <Kpi label="Gecikmiş" value={nf.format(overdue)} help="Termini geçmiş açık görev" />
            <Kpi label="Bu hafta" value={nf.format(week)} help="Termini 7 gün içinde" />
            <Kpi label="Termini yok" value={nf.format(undated)} help="Açık, termin girilmemiş" />
          </KpiRow>
          <div role="tablist" aria-label="Görev sütunu" className="-mx-1 flex gap-1 overflow-x-auto px-1 lg:hidden">
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
                <h3 className="flex items-baseline justify-between px-1 text-[13px] font-extrabold">
                  {STATUS_LABEL[s]}
                  <span className="font-mono text-[12px] tabular-nums text-canvas-muted">{nf.format(byStatus(s).length)}</span>
                </h3>
                {s === 'tamamlandi' && <p className="px-1 text-[11px] text-canvas-muted">Son 30 gün, iptaller dahil</p>}
                <ul className="zk-scroll mt-2 max-h-[520px] space-y-2 overflow-y-auto overscroll-contain">
                  {byStatus(s).map((t) => (
                    <TaskCard key={t.projectId} t={t} onOpen={() => setOpenId(t.projectId)} />
                  ))}
                </ul>
                {!byStatus(s).length && <p className="py-6 text-center text-[12px] text-canvas-muted">Boş</p>}
              </section>
            ))}
          </div>
        </>
      )}
      <Sheet
        open={!!current}
        onOpenChange={(o) => !o && setOpenId('')}
        title={current?.projectName || 'Görev'}
        sub={current ? [current.category, current.project?.status && `CRM: ${crmLabel(current.project.status)}`].filter(Boolean).join(' · ') : undefined}
      >
        {current && <TaskEditor key={current.projectId} task={current} onDone={() => setOpenId('')} />}
      </Sheet>
    </section>
  );
}
