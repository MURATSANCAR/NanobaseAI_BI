import { keepPreviousData, useQuery } from '@tanstack/react-query';
import { FileDiff, Loader2, TriangleAlert } from 'lucide-react';
import { Link } from 'react-router-dom';
import { canSeePage, usePageAccess } from '../../../useAdmin';
import { useDebounced } from '../../kit';
import type { Terms } from '../api';
import { errMsg } from '../ui';
import { compareApi } from './api';
import { isDeviation } from './compare';

/**
 * İmzadan önce: formda girilen şartlar (kaydedilmeden) benzer geçmiş sözleşmelerle kıyaslanır ve şekil denetiminden
 * geçer. Yazmayı bekler (700 ms), kayıt tutmaz. Karşılaştırma sayfası yetkisi yoksa görünmez.
 */
export default function TermsCheck({ terms, contractKey }: { terms: Terms; contractKey?: string }) {
  const allowed = canSeePage(usePageAccess(), 'sozlesme-karsilastirma');
  const key = useDebounced(JSON.stringify(terms), 700);
  const q = useQuery({
    queryKey: ['contracts', 'compare', 'terms', key],
    queryFn: () => compareApi.terms(JSON.parse(key) as Terms),
    enabled: allowed,
    placeholderData: keepPreviousData,
    staleTime: 60_000,
  });
  if (!allowed) return null;
  const d = q.data;
  const devs = d ? d.groups.flatMap((g) => g.clauses).filter((c) => isDeviation(c.status)) : [];
  const fails = d ? d.sekil.filter((x) => !x.ok) : [];
  return (
    <section className="rounded-2xl border border-violet-100 bg-violet-50/40 p-3" aria-live="polite">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <h3 className="flex items-center gap-1.5 text-[13px] font-extrabold">
          <FileDiff aria-hidden className="h-4 w-4 text-canvas-violet" />
          Emsal kontrolü
          {q.isFetching && <Loader2 aria-hidden className="h-3.5 w-3.5 animate-spin text-canvas-muted" />}
        </h3>
        {contractKey && (
          <Link to={`/telif-sozlesme/karsilastirma?sekme=sozlesme&sozlesme=${encodeURIComponent(contractKey)}`}
            className="inline-flex min-h-11 items-center text-[12px] font-bold text-canvas-violet hover:underline sm:min-h-0">
            Ayrıntılı karşılaştırma
          </Link>
        )}
      </div>
      <p className="mt-0.5 text-[11.5px] leading-snug text-canvas-muted">
        Girdiğiniz şartlar kaydedilmeden benzer geçmiş sözleşmelerle kıyaslanır{d ? ` (${d.criteria.emsal} emsal)` : ''}.
      </p>
      {q.error && <p className="mt-2 text-[12px] text-rose-700">{errMsg(q.error)}</p>}
      {d && !devs.length && !fails.length && <p className="mt-2 text-[12.5px] font-semibold text-emerald-800">Girilen şartlar emsalle uyumlu; şekil eksiği yok.</p>}
      {devs.length > 0 && (
        <ul className="mt-2 space-y-1.5">
          {devs.map((c) => (
            <li key={c.key} className="rounded-xl bg-white/90 p-2 text-[12px]">
              <div className="flex flex-wrap items-center gap-x-2">
                <span className="font-bold">{c.label}</span>
                <span className="font-mono tabular-nums">{c.valueLabel}</span>
                <span className="rounded-md bg-rose-50 px-1.5 text-[11px] font-bold text-rose-800">{c.statusLabel}</span>
              </div>
              {c.reason && <p className="mt-0.5 text-[11.5px] text-canvas-muted">{c.reason}</p>}
            </li>
          ))}
        </ul>
      )}
      {fails.length > 0 && (
        <ul className="mt-2 space-y-1">
          {fails.map((x) => (
            <li key={x.id} className="flex gap-1.5 text-[12px]">
              <TriangleAlert aria-hidden className="mt-0.5 h-3.5 w-3.5 shrink-0 text-amber-600" />
              <span><span className="font-bold">{x.label}:</span> {x.detail}</span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
