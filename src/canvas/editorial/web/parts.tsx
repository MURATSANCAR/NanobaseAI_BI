import { useQuery } from '@tanstack/react-query';
import { ExternalLink, Newspaper } from 'lucide-react';
import { ENGINE_ENABLED, webApi, type WebMention, type WebTone } from '../../engine';
import { nf } from '../../admin/ui';
import { dateTime } from '../../format';

/** Basın ve web: yalnız yerel modelin "bu yazar/kitap hakkında" dediği haberler (olumlu, olumsuz, nötr). */

export const TONE: Record<string, { label: string; cls: string }> = {
  olumlu: { label: 'Olumlu', cls: 'bg-emerald-50 text-emerald-700' },
  olumsuz: { label: 'Olumsuz', cls: 'bg-red-50 text-red-700' },
  notr: { label: 'Nötr', cls: 'bg-slate-100 text-canvas-ink' },
};

export function ToneBar({ tone }: { tone: WebTone }) {
  const total = (tone.olumlu ?? 0) + (tone.olumsuz ?? 0) + (tone.notr ?? 0);
  if (!total) return null;
  const parts: Array<[string, number, string]> = [
    ['olumlu', tone.olumlu ?? 0, 'bg-canvas-mint'],
    ['notr', tone.notr ?? 0, 'bg-slate-300'],
    ['olumsuz', tone.olumsuz ?? 0, 'bg-canvas-coral'],
  ];
  return (
    <div>
      <div className="flex h-2 overflow-hidden rounded-full" role="img" aria-label={parts.map(([k, n]) => `${TONE[k].label} ${n}`).join(', ')}>
        {parts.map(([k, n, c]) => (n ? <span key={k} className={c} style={{ width: `${(n / total) * 100}%` }} /> : null))}
      </div>
      <div className="mt-1 flex flex-wrap gap-x-3 text-[11px] text-canvas-muted">
        {parts.map(([k, n]) => (
          <span key={k}>
            {TONE[k].label} <b className="font-mono tabular-nums text-canvas-ink">{nf.format(n)}</b>
          </span>
        ))}
      </div>
    </div>
  );
}

export function MentionRow({ m, showAuthor }: { m: WebMention; showAuthor?: boolean }) {
  const t = TONE[m.label];
  return (
    <li className="border-t border-slate-100 py-2.5 first:border-t-0">
      <a href={m.url} target="_blank" rel="noopener noreferrer" className="group block">
        <span className="flex items-start justify-between gap-2">
          <span className="min-w-0 break-words text-[13px] font-extrabold leading-snug group-hover:underline">{m.title}</span>
          <ExternalLink aria-hidden className="mt-0.5 h-3.5 w-3.5 shrink-0 text-canvas-muted" />
        </span>
        {m.summary && <span className="mt-0.5 block text-[12px] leading-snug text-canvas-muted">{m.summary}</span>}
      </a>
      <span className="mt-1.5 flex flex-wrap items-center gap-x-2 gap-y-1 text-[11px] text-canvas-muted">
        {t && <span className={`rounded-md px-1.5 py-0.5 font-bold ${t.cls}`}>{t.label}</span>}
        <span className="font-semibold text-canvas-ink">{m.source}</span>
        <span className="font-mono tabular-nums">{dateTime(m.on)}</span>
        {showAuthor && <span>· {m.author}</span>}
        {m.books.map((b) => (
          <span key={b.id}>· «{b.title}»</span>
        ))}
      </span>
    </li>
  );
}

/** Kişi ya da kitap sayfasına eklenen "Basında" bölümü. Kayıt yoksa hiç çizilmez (gereksiz bilgi yok). */
export function WebSection({ kind, id, framed }: { kind: 'person' | 'book'; id: string; framed?: boolean }) {
  const q = useQuery({
    queryKey: ['editorial', 'web', kind, id],
    queryFn: () => (kind === 'person' ? webApi.person(id) : webApi.book(id)),
    enabled: ENGINE_ENABLED && !!id,
    staleTime: 5 * 60_000,
  });
  const d = q.data;
  if (!d || (!d.total && !d.facts)) return null;
  const f = d.facts;
  return (
    <section className={framed ? 'glass-panel rounded-2xl p-3 shadow-glass-float sm:rounded-3xl sm:p-4' : 'mt-4'}>
      <h3 className={`flex items-center gap-1.5 font-extrabold ${framed ? 'text-[14px]' : 'text-[12px]'}`}>
        <Newspaper aria-hidden className="h-3.5 w-3.5 text-canvas-violet" />
        Basında ve web'de
        {d.total > 0 && <span className="font-mono font-semibold tabular-nums text-canvas-muted">{nf.format(d.total)}</span>}
      </h3>
      {f && (
        <div className="mt-1.5 rounded-xl bg-slate-50 px-3 py-2 text-[12px] leading-snug">
          {f.description && <div className="font-semibold">{f.description}</div>}
          <div className="text-canvas-muted">
            {[f.born && `${f.born}${f.died ? `–${f.died}` : ''}`, f.occupations.slice(0, 3).join(', ')].filter(Boolean).join(' · ')}
          </div>
          {f.awards.length > 0 && <div className="mt-1">Ödüller: {f.awards.join(', ')}</div>}
          <div className="mt-1 flex gap-3 text-[11px] font-bold">
            {f.wikipedia && (
              <a className="text-canvas-violet hover:underline" href={f.wikipedia} target="_blank" rel="noopener noreferrer">
                Vikipedi
              </a>
            )}
            <a className="text-canvas-violet hover:underline" href={f.wikidata} target="_blank" rel="noopener noreferrer">
              Wikidata
            </a>
          </div>
        </div>
      )}
      {d.total > 0 && (
        <>
          <div className="mt-2">
            <ToneBar tone={d.tone} />
          </div>
          <ul className="mt-1.5 max-h-80 overflow-y-auto pr-1">
            {d.items.map((m) => (
              <MentionRow key={`${m.url}-${m.contactId}`} m={m} />
            ))}
          </ul>
        </>
      )}
    </section>
  );
}
