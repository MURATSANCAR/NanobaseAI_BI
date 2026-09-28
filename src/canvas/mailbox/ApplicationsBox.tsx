import { Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { Mail } from 'lucide-react';
import { ENGINE_ENABLED } from '../engine';
import { fmtInt, fmtWhen, mailApi } from './api';

/** Yazar giriş süreci panosundaki «E-postayla gelen başvurular» kutusu (H4 sözleşme ucu `GET /api/v1/mailbox/applications`).
 *  Aktarılmayı bekleyen başvuru yoksa ya da uç bu kurulumda yoksa hiç görünmez. */
export default function MailApplicationsBox() {
  const q = useQuery({ queryKey: ['mailbox', 'applications', 'yeni'], queryFn: () => mailApi.applications('yeni'), enabled: ENGINE_ENABLED, retry: false, staleTime: 60_000 });
  const d = q.data;
  if (!d || d.total === 0) return null;
  return (
    <details className="glass-panel rounded-2xl px-3 py-2 shadow-glass-float sm:px-4">
      <summary className="flex min-h-11 cursor-pointer list-none items-center gap-2 text-[13px] font-extrabold">
        <Mail aria-hidden className="h-4 w-4 text-canvas-violet" />
        E-postayla gelen başvurular
        <span className="rounded-md bg-canvas-violet/10 px-1.5 py-0.5 font-mono text-[11px] tabular-nums text-canvas-violet">{fmtInt(d.total)}</span>
        <span className="ml-auto text-[11.5px] font-semibold text-canvas-muted">aktarılmayı bekliyor</span>
      </summary>
      <ul className="mt-1 flex flex-col gap-1 pb-1">
        {d.items.map((a) => (
          <li key={a.messageId}>
            <Link to={`/kurumsal-eposta/ileti/${a.messageId}`} className="block rounded-lg px-2 py-1.5 text-[12px] hover:bg-slate-50">
              <span className="block truncate font-bold">{a.workTitle || a.subject || '(konusuz)'}</span>
              <span className="text-canvas-muted">
                {a.authorName || a.fromName || a.fromMasked} · {fmtWhen(a.receivedAt)}
                {a.attachments.length ? ` · ${a.attachments.length} ek` : ''}
              </span>
            </Link>
          </li>
        ))}
      </ul>
    </details>
  );
}
