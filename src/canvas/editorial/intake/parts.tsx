import { Link } from 'react-router-dom';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { Check } from 'lucide-react';
import { intakeApi, type IntakeCard } from '../../engine';
import { btnPrimary, nf } from '../../admin/ui';
import { dateTime } from '../../format';

/** Yazar giriş sürecinin ortak parçaları: 9 adımlık ilerleme çizgisi, proje kartı, işaretleme düğmesi. */

/** Evrelerin adımları (1–3 değerlendirme, 4–5 kurul, 6–9 giriş); çizgide evreler arasına boşluk girer. */
const PHASE_OF = [1, 1, 1, 2, 2, 3, 3, 3, 3];

export function Progress({ card, size = 'sm' }: { card: Pick<IntakeCard, 'progress' | 'step' | 'late' | 'outcome'>; size?: 'sm' | 'md' }) {
  const h = size === 'md' ? 'h-2' : 'h-1.5';
  return (
    <div className="flex items-center" role="img" aria-label={`9 adımın ${card.progress.filter(Boolean).length} tanesi tamam`}>
      {card.progress.map((done, i) => {
        const current = card.step === i + 1 && !card.outcome;
        const tone = done ? 'bg-canvas-mint' : current ? (card.late ? 'bg-canvas-coral' : 'bg-canvas-violet') : 'bg-slate-200';
        const gap = i > 0 && PHASE_OF[i] !== PHASE_OF[i - 1] ? 'ml-2' : i > 0 ? 'ml-1' : '';
        return <span key={i} className={`${h} flex-1 rounded-full ${tone} ${gap}`} />;
      })}
    </div>
  );
}

export const waitingText = (c: Pick<IntakeCard, 'waitingDays'>) =>
  c.waitingDays == null ? '' : c.waitingDays === 0 ? 'bugün' : `${nf.format(c.waitingDays)} gün`;

/** "10 gündür bekliyor" / "bugün başladı". */
export const waitingSentence = (c: Pick<IntakeCard, 'waitingDays'>) =>
  c.waitingDays == null ? '' : c.waitingDays === 0 ? 'bugün başladı' : `${nf.format(c.waitingDays)} gündür bekliyor`;

export function ProjectCard({ c, showEditor }: { c: IntakeCard; showEditor?: boolean }) {
  return (
    <li>
      <Link
        to={`/yazar-giris/${c.id}`}
        className={`block rounded-2xl border bg-white/90 px-3 py-2.5 transition-transform duration-150 ease-out hover:bg-white active:scale-[0.98] ${
          c.late ? 'border-canvas-coral/40 shadow-[inset_3px_0_0_0_theme(colors.canvas.coral)]' : 'border-slate-100'
        }`}
      >
        <div className="flex items-start justify-between gap-2">
          <span className="min-w-0 break-words text-[13px] font-extrabold leading-snug">{c.name || 'Adsız proje'}</span>
          {c.mine && <span className="shrink-0 rounded-md bg-canvas-violet/10 px-1.5 py-0.5 text-[10.5px] font-bold text-canvas-violet">Sizde</span>}
        </div>
        <div className="mt-0.5 break-words text-[11.5px] leading-snug text-canvas-muted">
          {[c.author, showEditor && (c.editor ? `Editör: ${c.editor}` : 'Editör yok')].filter(Boolean).join(' · ') || 'Yazar girilmemiş'}
        </div>
        <div className="mt-2 flex items-baseline justify-between gap-2 text-[12px] leading-snug">
          <span className={`min-w-0 break-words font-semibold ${c.outcome ? 'text-canvas-muted' : c.late ? 'text-red-700' : c.complete ? 'text-emerald-700' : 'text-canvas-ink'}`}>
            {c.line}
            {c.late && <span className="ml-1.5 rounded bg-red-50 px-1 py-px text-[10.5px] font-bold text-red-700">Gecikti</span>}
          </span>
          <span className="shrink-0 font-mono text-[11.5px] tabular-nums text-canvas-muted">
            {c.outcome || c.complete ? dateTime(c.modifiedOn) : waitingText(c)}
          </span>
        </div>
        <div className="mt-2">
          <Progress card={c} />
        </div>
      </Link>
    </li>
  );
}

/** Portalda işaretlenen adım ("Rapor bitti", "Bildirdim"). CRM'de karşılığı yok; kayıt köprüde tutulur. */
export function MarkButton({ projectId, step, label, className = '' }: { projectId: string; step: number; label: string; className?: string }) {
  const qc = useQueryClient();
  const m = useMutation({
    mutationFn: () => intakeApi.mark(projectId, step),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['editorial', 'intake'] }),
  });
  return (
    <div className={className}>
      <button type="button" className={`${btnPrimary} w-full sm:w-auto`} disabled={m.isPending} onClick={() => m.mutate()}>
        <Check aria-hidden className="h-4 w-4" />
        {m.isPending ? 'Kaydediliyor…' : label}
      </button>
      {m.error && <p className="mt-1 text-[11.5px] font-semibold text-red-700">{(m.error as Error).message || 'Kaydedilemedi.'}</p>}
    </div>
  );
}

/** İşaretlenebilen adımda düğmenin söylediği şey. */
export const MARK_LABEL: Record<number, string> = { 3: 'Rapor bitti', 6: 'Yazara bildirdim' };

/** Yönetici görünümü: bütün editörlerin bekleyen işi, editöre göre. En çok geciken editör üstte; grup tıklanınca açılır. */
export function TodoGroups({ todo, openFirst = false }: { todo: IntakeCard[]; openFirst?: boolean }) {
  const groups = new Map<string, IntakeCard[]>();
  for (const c of todo) {
    const k = c.editor || 'Editör atanmamış';
    groups.set(k, [...(groups.get(k) ?? []), c]);
  }
  const rows = [...groups.entries()].sort((a, b) => b[1].filter((c) => c.late).length - a[1].filter((c) => c.late).length || b[1].length - a[1].length);
  return (
    <ul className="space-y-1.5">
      {rows.map(([editor, cards], i) => (
        <li key={editor}>
          <details open={openFirst && i === 0} className="group rounded-xl bg-white/90">
            <summary className="flex min-h-11 cursor-pointer list-none items-center justify-between gap-2 px-3 py-2 text-[12.5px] [&::-webkit-details-marker]:hidden">
              <span className="min-w-0 break-words font-extrabold">{editor}</span>
              <span className="flex shrink-0 items-center gap-1.5 font-mono text-[11.5px] tabular-nums">
                <span>{nf.format(cards.length)} iş</span>
                {cards.some((c) => c.late) && <span className="rounded bg-red-50 px-1 font-bold text-red-700">{nf.format(cards.filter((c) => c.late).length)} gecikti</span>}
              </span>
            </summary>
            <ul className="border-t border-slate-100 px-3 pb-2">
              {cards.map((c) => (
                <li key={c.id} className="border-t border-slate-100 first:border-t-0">
                  <Link to={`/yazar-giris/${c.id}`} className="flex flex-wrap items-baseline justify-between gap-x-3 py-1.5 text-[12px] hover:underline">
                    <span className="min-w-0 break-words">
                      <b className="font-extrabold">{c.name || 'Adsız proje'}</b>
                      <span className="text-canvas-muted"> — {c.line.charAt(0).toLocaleLowerCase('tr') + c.line.slice(1)}</span>
                    </span>
                    <span className={`shrink-0 font-mono text-[11px] tabular-nums ${c.late ? 'font-bold text-red-700' : 'text-canvas-muted'}`}>{waitingText(c)}</span>
                  </Link>
                </li>
              ))}
            </ul>
          </details>
        </li>
      ))}
    </ul>
  );
}
