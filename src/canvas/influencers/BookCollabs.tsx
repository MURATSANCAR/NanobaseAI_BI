import { Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { Pill } from '../admin/ui';
import { ENGINE_ENABLED } from '../engine';
import SqlInfo from '../components/SqlInfo';
import { Panel } from '../editorial/kit';
import { canOpenRoute, usePageAccess } from '../useAdmin';
import { STAGE_TONE, fmtDay, fmtInt, inflApi } from './api';

/** Kitap sayfasındaki «İşbirlikleri» bölümü (M23). İşbirlikleri sayfası rolde yoksa hiç çizilmez. */
export default function BookCollabs({ bookId }: { bookId: string }) {
  const pages = usePageAccess();
  const allowed = pages !== null && canOpenRoute(pages, '/isbirlikleri');
  const q = useQuery({ queryKey: ['influencers', 'book', bookId], queryFn: () => inflApi.bookCollabs(bookId), enabled: ENGINE_ENABLED && allowed });
  if (!allowed || !q.data) return null;
  const d = q.data;
  return (
    <Panel>
      <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
        <h2 className="flex items-center gap-1 text-[13px] font-extrabold">İşbirlikleri<SqlInfo k={d.kaynaklar} alan="items" label="Kitabın işbirlikleri" /></h2>
        <Link to={`/isbirlikleri/aday/${bookId}`} className="text-[12px] font-bold text-canvas-violet hover:underline">Aday içerik üreticileri</Link>
      </div>
      {d.items.length === 0 ? (
        <div className="text-[12.5px] text-canvas-muted">Bu kitapla içerik üreticisi işbirliği yok.</div>
      ) : (
        <>
          <div className="mb-2 text-[12px] text-canvas-muted">{d.published} yayında · {fmtInt(d.engagement)} etkileşim · {fmtInt(d.reach)} erişim</div>
          <ul className="flex flex-col gap-1">
            {d.items.map((c) => (
              <li key={c.id}>
                <Link to={`/isbirlikleri?is=${c.id}`} className="flex min-h-10 flex-wrap items-center gap-2 rounded-xl px-2 py-1 text-[12.5px] hover:bg-slate-50">
                  <Pill tone={STAGE_TONE[c.stage]}>{c.stageLabel}</Pill>
                  <span className="font-bold">{c.personName}</span>
                  <span className="text-canvas-muted">{c.kindLabel} · {fmtDay(c.publishedAt ?? c.duePublish)}</span>
                </Link>
              </li>
            ))}
          </ul>
        </>
      )}
    </Panel>
  );
}
