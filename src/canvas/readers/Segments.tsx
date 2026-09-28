import { useState } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { Plus } from 'lucide-react';
import { ENGINE_ENABLED } from '../engine';
import { Loading, Note, Pill, Section, btnPrimary, errText } from '../admin/ui';
import { fmtDay, fmtInt, readersApi, SEGMENT_TONE, type SegmentStatus } from './api';
import { ROOT, useMeta } from './parts';
import SegmentBuilder from './SegmentBuilder';

const FILTERS: Array<{ id: string; label: string }> = [
  { id: '', label: 'Etkin' },
  { id: 'onay-bekliyor', label: 'Onay bekleyen' },
  { id: 'onayli', label: 'Onaylı' },
  { id: 'taslak', label: 'Taslak' },
  { id: 'arsiv', label: 'Arşiv' },
];

/** Segmentler: liste (/okurlar/segmentler), yeni (/yeni), segment (/:id). */
export default function Segments() {
  const { pathname } = useLocation();
  const rest = pathname.replace(/\/+$/, '').slice(`${ROOT}/segmentler`.length).replace(/^\//, '');
  if (rest === 'yeni') return <SegmentBuilder />;
  if (rest) return <SegmentBuilder id={decodeURIComponent(rest)} />;
  return <SegmentList />;
}

function SegmentList() {
  const [filter, setFilter] = useState('');
  const meta = useMeta();
  const q = useQuery({ queryKey: ['readers', 'segments', filter], queryFn: () => readersApi.segments(filter), enabled: ENGINE_ENABLED });
  const me = meta.data?.me;
  return (
    <Section
      title="Segmentler"
      help="Kurala dayalı okur grupları. Sayılar kuralın kendisinden hesaplanır; onaylı segment gece sayılır ve dışa aktarılabilir."
      action={me?.canSegment ? <Link to={`${ROOT}/segmentler/yeni`} className={btnPrimary}><Plus aria-hidden className="h-4 w-4" />Yeni segment</Link> : undefined}
    >
      <div className="flex flex-wrap gap-1">
        {FILTERS.map((f) => (
          <button key={f.id} type="button" aria-pressed={filter === f.id} onClick={() => setFilter(f.id)}
            className={`min-h-11 rounded-xl px-3 text-[12.5px] font-extrabold transition-colors duration-150 sm:min-h-9 ${filter === f.id ? 'bg-canvas-violet text-white' : 'bg-slate-100 hover:bg-slate-200'}`}>
            {f.label}
          </button>
        ))}
      </div>
      {q.isLoading && <Loading />}
      {q.error && <Note tone="err">{errText(q.error, 'Segmentler açılamadı.')}</Note>}
      {q.data && q.data.items.length === 0 && <Note tone="info">Bu durumda segment yok.</Note>}
      <ul className="grid gap-2 lg:grid-cols-2">
        {q.data?.items.map((s) => (
          <li key={s.id}>
            <Link to={`${ROOT}/segmentler/${s.id}`} className="flex h-full flex-col gap-1.5 rounded-2xl border border-slate-100 bg-white/80 p-3 transition-colors duration-150 hover:bg-white">
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-[14px] font-extrabold">{s.name}</span>
                <Pill tone={SEGMENT_TONE[s.status as SegmentStatus]}>{s.statusLabel}</Pill>
                <span className="font-mono text-[11px] text-canvas-muted">v{s.version}</span>
                {s.origin === 'zeki' && <Pill tone="violet">Zeki AI önerisi</Pill>}
              </div>
              <p className="text-[12px] leading-snug text-canvas-muted">{s.explanation}</p>
              <div className="mt-auto flex flex-wrap gap-x-3 text-[11.5px] font-semibold text-canvas-muted">
                {s.lastSnapshot ? (
                  <>
                    <span>{fmtInt(s.lastSnapshot.total)} okur</span>
                    <span>e-posta {fmtInt(s.lastSnapshot.email)}</span>
                    <span>SMS {fmtInt(s.lastSnapshot.sms)}</span>
                    <span>sayım {fmtDay(s.lastSnapshot.at)}</span>
                  </>
                ) : <span>{s.owner} · {fmtDay(s.updatedAt)}</span>}
              </div>
            </Link>
          </li>
        ))}
      </ul>
    </Section>
  );
}
