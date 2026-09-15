import { useState } from 'react';
import { useInfiniteQuery } from '@tanstack/react-query';
import { ChevronDown, Search } from 'lucide-react';
import { adminApi, type AuditItem } from '../engine';
import { ACTION_LABEL, FIELD_LABEL, Loading, Note, Pill, Section, btnGhost, errText, field, fmtDate, show } from './ui';

const KINDS = [
  ['', 'Her tür'],
  ['report', 'Planlı rapor'],
  ['alert', 'Uyarı'],
  ['board', 'Pano kartı'],
  ['setting', 'Ayar'],
  ['term', 'Sözlük terimi'],
  ['annotation', 'Kolon açıklaması'],
] as const;
const ACTIONS = [
  ['', 'Her işlem'],
  ['create', 'Oluşturma'],
  ['update', 'Güncelleme'],
  ['delete', 'Silme'],
  ['run', 'Çalıştırma'],
  ['approve', 'Onay'],
  ['reject', 'Ret'],
  ['correct', 'Düzeltme'],
] as const;

/** Ayrıntı: {alan: {from, to}} farkı ya da düz alanlar. */
function Detail({ d }: { d: Record<string, unknown> }) {
  const entries = Object.entries(d);
  return (
    <dl className="mt-2 space-y-1 rounded-xl bg-slate-50 p-2.5 text-[11.5px]">
      {entries.map(([k, v]) => {
        const diff = v && typeof v === 'object' && !Array.isArray(v) && ('from' in v || 'to' in v) ? (v as { from: unknown; to: unknown }) : null;
        return (
          <div key={k} className="grid gap-x-2 sm:grid-cols-[120px_1fr]">
            <dt className="font-bold text-canvas-muted">{FIELD_LABEL[k] ?? k}</dt>
            <dd className="min-w-0 break-words">
              {diff ? (
                <>
                  <span className="text-red-700 line-through decoration-red-300">{show(diff.from)}</span>
                  <span className="px-1.5 text-canvas-muted">→</span>
                  <span className="font-semibold text-emerald-700">{show(diff.to)}</span>
                </>
              ) : (
                show(v)
              )}
            </dd>
          </div>
        );
      })}
    </dl>
  );
}

export function AuditRow({ item }: { item: AuditItem }) {
  const [open, setOpen] = useState(false);
  const a = ACTION_LABEL[item.action] ?? { label: item.action, tone: 'muted' as const };
  const hasDetail = !!item.detail && Object.keys(item.detail).length > 0;
  return (
    <li className="py-2">
      <button
        type="button"
        onClick={() => hasDetail && setOpen((o) => !o)}
        aria-expanded={hasDetail ? open : undefined}
        className={`flex w-full min-w-0 items-start gap-3 text-left ${hasDetail ? 'cursor-pointer' : 'cursor-default'}`}
      >
        <span className="w-24 shrink-0 pt-0.5 text-[11px] tabular-nums text-canvas-muted">{fmtDate(item.at)}</span>
        <span className="min-w-0 flex-1">
          <span className="flex flex-wrap items-center gap-1.5 text-[12.5px]">
            <span className="font-bold">{item.actor}</span>
            <Pill tone={a.tone}>{a.label}</Pill>
            <span className="text-canvas-muted">{item.kindLabel}</span>
          </span>
          <span className="block truncate text-[12.5px] font-semibold">{item.title || item.objectId || '—'}</span>
          {open && item.detail && <Detail d={item.detail} />}
        </span>
        {hasDetail && (
          <ChevronDown className={`mt-1 h-4 w-4 shrink-0 text-canvas-muted transition-transform duration-200 ease-out ${open ? 'rotate-180' : ''}`} />
        )}
      </button>
    </li>
  );
}

export default function AuditLog() {
  const [kind, setKind] = useState('');
  const [action, setAction] = useState('');
  const [text, setText] = useState('');
  const [search, setSearch] = useState('');

  const q = useInfiniteQuery({
    queryKey: ['admin', 'audit', kind, action, search],
    queryFn: ({ pageParam }) => adminApi.audit({ kind, action, q: search, before: pageParam ?? undefined }),
    initialPageParam: null as number | null,
    getNextPageParam: (last) => last.next,
    retry: false,
  });
  const items = q.data?.pages.flatMap((p) => p.items) ?? [];

  return (
    <Section title="Değişiklik kaydı" help="Kim, ne zaman, neyi oluşturdu, güncelledi, sildi ya da çalıştırdı. Satıra dokununca değişen alanlar görünür.">
      <div className="flex flex-col gap-2 sm:flex-row">
        <form
          className="relative flex-1"
          onSubmit={(e) => {
            e.preventDefault();
            setSearch(text.trim());
          }}
        >
          <Search className="pointer-events-none absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-canvas-muted" />
          <input value={text} onChange={(e) => setText(e.target.value)} onBlur={() => setSearch(text.trim())} placeholder="Başlık, kişi ya da kimlik ara…" className={`${field} pl-8`} />
        </form>
        <select value={kind} onChange={(e) => setKind(e.target.value)} className={`${field} sm:w-44`} aria-label="Tür">
          {KINDS.map(([v, l]) => (
            <option key={v} value={v}>
              {l}
            </option>
          ))}
        </select>
        <select value={action} onChange={(e) => setAction(e.target.value)} className={`${field} sm:w-40`} aria-label="İşlem">
          {ACTIONS.map(([v, l]) => (
            <option key={v} value={v}>
              {l}
            </option>
          ))}
        </select>
      </div>
      {q.isLoading ? (
        <Loading />
      ) : q.error ? (
        <Note tone="err">{errText(q.error, 'Kayıt okunamadı.')}</Note>
      ) : items.length ? (
        <div className="rounded-2xl border border-slate-100 bg-white/80 px-4">
          <ul className="divide-y divide-slate-100">
            {items.map((a) => (
              <AuditRow key={a.id} item={a} />
            ))}
          </ul>
        </div>
      ) : (
        <Note tone="info">Bu süzgece uyan kayıt yok.</Note>
      )}
      {q.hasNextPage && (
        <button type="button" onClick={() => q.fetchNextPage()} disabled={q.isFetchingNextPage} className={btnGhost}>
          {q.isFetchingNextPage ? 'Yükleniyor…' : 'Daha eski kayıtlar'}
        </button>
      )}
    </Section>
  );
}
