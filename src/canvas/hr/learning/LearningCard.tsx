import { Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { GraduationCap } from 'lucide-react';
import { ENGINE_ENABLED } from '../../engine';
import { canSeePage, usePageAccess } from '../../useAdmin';
import { learningApi } from './learningApi';
import { fmtDay, fmtWhen } from './parts';

/** Kampüs «Eğitimlerim» kısa kartı (M57): yaklaşan oturumum, süresi dolan/dolacak zorunlu eğitimim, bekleyen anketim.
 *  Yalnız kişinin kendi kaydı; sayfa rolünde yoksa ya da gösterecek bir şey yoksa kart hiç çizilmez. */
export default function LearningCard({ className = '' }: { className?: string }) {
  const pages = usePageAccess();
  const allowed = canSeePage(pages, 'ik-egitimlerim');
  const q = useQuery({ queryKey: ['hr', 'learning', 'me'], queryFn: learningApi.me, enabled: ENGINE_ENABLED && allowed, retry: false, staleTime: 5 * 60_000 });
  const d = q.data;
  if (!allowed || !d?.employee) return null;
  const upcoming = d.enrollments.filter((e) => e.sessionState === 'planli' && e.approval === 'onaylandi').sort((a, b) => a.startsAt.localeCompare(b.startsAt));
  const due = d.mandatory.filter((m) => m.status !== 'gecerli');
  if (!upcoming.length && !due.length && !d.feedback.length) return null;
  return (
    <section id="egitimlerim" className={`kp-card rounded-3xl border border-white/80 bg-white/90 p-4 ${className}`}>
      <div className="mb-3 flex items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <GraduationCap className="h-4 w-4 text-teal-700" aria-hidden />
          <h3 className="kp-display text-xs font-bold uppercase tracking-wider text-ink">Eğitimlerim</h3>
        </div>
        <Link to="/ik/egitimlerim" className="shrink-0 text-[11px] font-medium text-violet hover:underline">Aç</Link>
      </div>
      <ul className="space-y-2 text-xs">
        {upcoming.slice(0, 2).map((e) => (
          <li key={e.id}>
            <div className="font-semibold text-ink">{e.courseTitle}</div>
            <div className="text-[11px] text-muted">{fmtWhen(e.startsAt)}{e.location ? ` · ${e.location}` : ''}</div>
          </li>
        ))}
        {due.slice(0, 2).map((m) => (
          <li key={m.courseId}>
            <div className="font-semibold text-rose-700">{m.courseTitle}</div>
            <div className="text-[11px] text-muted">{m.statusLabel}{m.expiresOn ? ` · ${fmtDay(m.expiresOn)}` : ''}</div>
          </li>
        ))}
        {d.feedback.length > 0 && <li className="text-[11px] font-semibold text-violet">{d.feedback.length} anket sizi bekliyor</li>}
      </ul>
    </section>
  );
}
