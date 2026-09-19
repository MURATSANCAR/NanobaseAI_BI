import { useEffect, useState } from 'react';
import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { AlertTriangle, Check, Copy, Download, FileDown, Search, X } from 'lucide-react';
import { adminApi, type PromptDetail, type PromptRow } from '../engine';
import { Loading, Note, Pill, Section, TableWrap, btnGhost, errText, field, fmtDate, nf, td, th } from './ui';

/** Cevap tipi → okunur etiket + renk. Başarısız/eksik olanlar göze çarpsın. */
const TYPE: Record<string, { label: string; tone: 'ok' | 'warn' | 'err' | 'muted' | 'violet' }> = {
  TEXT_TO_SQL: { label: 'Cevaplandı', tone: 'ok' },
  CLARIFICATION: { label: 'Netleştirme', tone: 'warn' },
  INCOMPLETE_ANSWER: { label: 'Eksik', tone: 'warn' },
  NON_SQL_QUERY: { label: 'SQL yok', tone: 'muted' },
  SQL_INVALID: { label: 'SQL geçersiz', tone: 'err' },
  DATA_UNAVAILABLE: { label: 'Veri kapsam dışı', tone: 'muted' },
  DATA_SOURCE_UNAVAILABLE: { label: 'Kaynak ulaşılamaz', tone: 'err' },
  MODULE_INTRO: { label: 'Tanıtım', tone: 'muted' },
};
const typeInfo = (t: string | null) => TYPE[t ?? ''] ?? { label: t ?? '—', tone: 'muted' as const };

const FLAG: Record<string, { label: string; tone: 'ok' | 'warn' | 'err' | 'muted' | 'violet' }> = {
  todo: { label: 'Düzeltilecek', tone: 'err' },
  fixed: { label: 'Düzeltildi', tone: 'ok' },
  ignored: { label: 'Önemsiz', tone: 'muted' },
};

const FILTERS: Array<[string, string]> = [
  ['', 'Hepsi'],
  ['failed', 'Başarısız'],
  ['answered', 'Cevaplanan'],
  ['clarification', 'Netleştirme'],
  ['todo', 'Düzeltilecek'],
  ['reviewed', 'İncelenen'],
];
const DAYS: Array<[string, string]> = [
  ['7', '7 gün'],
  ['30', '30 gün'],
  ['90', '90 gün'],
  ['', 'Tümü'],
];

function Stat({ label, value, tone }: { label: string; value: number; tone: 'ink' | 'ok' | 'err' | 'violet' }) {
  const color = { ink: 'text-canvas-ink', ok: 'text-emerald-600', err: 'text-red-600', violet: 'text-canvas-violet' }[tone];
  return (
    <div className="rounded-2xl border border-slate-100 bg-white/80 px-4 py-3">
      <div className="text-[11px] font-bold uppercase tracking-wide text-canvas-muted">{label}</div>
      <div className={`mt-0.5 text-2xl font-extrabold tabular-nums ${color}`}>{nf.format(value)}</div>
    </div>
  );
}

function CopyBtn({ text }: { text: string }) {
  const [done, setDone] = useState(false);
  return (
    <button
      type="button"
      onClick={() => {
        navigator.clipboard?.writeText(text).then(() => {
          setDone(true);
          setTimeout(() => setDone(false), 2000);
        });
      }}
      className={`${btnGhost} !min-h-0 !px-2 !py-1 !text-[11px]`}
    >
      {done ? <Check className="h-3.5 w-3.5" /> : <Copy className="h-3.5 w-3.5" />}
      {done ? 'Kopyalandı' : 'Kopyala'}
    </button>
  );
}

function ResultTable({ result }: { result: NonNullable<PromptDetail['result']> }) {
  const cols = result.columns ?? [];
  const rows = result.records ?? [];
  const shown = rows.slice(0, 200);
  if (!cols.length) return <Note tone="info">Bu cevapta saklı sonuç satırı yok.</Note>;
  return (
    <div className="space-y-1">
      <TableWrap>
        <thead>
          <tr>
            {cols.map((c) => (
              <th key={c.name} className={th}>
                {c.name}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100">
          {shown.map((r, i) => (
            <tr key={i}>
              {cols.map((c) => (
                <td key={c.name} className={`${td} whitespace-nowrap tabular-nums`}>
                  {r[c.name] === null || r[c.name] === undefined ? '—' : String(r[c.name])}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </TableWrap>
      <p className="text-[11px] text-canvas-muted">
        {result._truncated_store
          ? 'Sonuç çok büyük olduğu için satırlar saklanmadı; yalnız başlık ve sayım tutuldu.'
          : `${nf.format(rows.length)} satır saklandı${rows.length > shown.length ? `, ilk ${shown.length} gösteriliyor` : ''}.`}
      </p>
    </div>
  );
}

function Detail({ id, onClose }: { id: string; onClose: () => void }) {
  const qc = useQueryClient();
  const [note, setNote] = useState('');
  const [noteInit, setNoteInit] = useState(false);
  const q = useQuery({ queryKey: ['admin', 'prompt', id], queryFn: () => adminApi.prompt(id), retry: false });
  const d = q.data;
  useEffect(() => {
    if (d && !noteInit) {
      setNote(d.reviewNote ?? '');
      setNoteInit(true);
    }
  }, [d, noteInit]);

  const mark = useMutation({
    mutationFn: (b: { flag?: string; note?: string }) => adminApi.markPrompt(id, b),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['admin', 'prompt', id] });
      qc.invalidateQueries({ queryKey: ['admin', 'prompts'] });
      qc.invalidateQueries({ queryKey: ['admin', 'prompts', 'overview'] });
    },
  });

  const t = d ? typeInfo(d.answerType) : null;
  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-black/40 p-0 sm:items-center sm:p-4" onClick={onClose}>
      <div
        role="dialog"
        aria-modal="true"
        aria-label="Promt ayrıntısı"
        tabIndex={-1}
        ref={(el) => el?.focus()}
        onKeyDown={(e) => {
          if (e.key === 'Escape') onClose();
        }}
        className="flex max-h-[92vh] w-full max-w-3xl flex-col overflow-hidden rounded-t-3xl bg-white shadow-2xl outline-none sm:rounded-3xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-start justify-between gap-3 border-b border-slate-100 px-4 py-3 sm:px-6">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-1.5">
              {t && <Pill tone={t.tone}>{t.label}</Pill>}
              {d?.reviewFlag && <Pill tone={FLAG[d.reviewFlag].tone}>{FLAG[d.reviewFlag].label}</Pill>}
              {d?.compiler && <span className="text-[11px] font-semibold text-canvas-muted">{d.compiler}</span>}
            </div>
            <h3 className="mt-1 break-words text-[15px] font-extrabold leading-snug">{d?.question ?? '…'}</h3>
            <div className="mt-0.5 text-[11.5px] text-canvas-muted">
              {d?.username ?? 'oturumsuz'} · {fmtDate(d?.createdAt)}
              {d?.latencyMs != null && ` · ${nf.format(d.latencyMs)} ms`}
              {d?.rowCount != null && ` · ${nf.format(d.rowCount)} satır`}
            </div>
          </div>
          <button type="button" onClick={onClose} aria-label="Kapat" className={`${btnGhost} !min-h-0 !p-2`}>
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="min-h-0 flex-1 space-y-4 overflow-y-auto px-4 py-4 sm:px-6">
          {q.isLoading ? (
            <Loading />
          ) : q.error || !d ? (
            <Note tone="err">{errText(q.error, 'Promt okunamadı.')}</Note>
          ) : (
            <>
              {d.answerSummary && (
                <section>
                  <div className="mb-1 text-[11px] font-bold uppercase tracking-wide text-canvas-muted">Cevap / özet</div>
                  <p className="whitespace-pre-wrap rounded-xl bg-slate-50 p-3 text-[12.5px] leading-relaxed">{d.answerSummary}</p>
                </section>
              )}
              {d.error && (
                <section>
                  <div className="mb-1 flex items-center gap-1 text-[11px] font-bold uppercase tracking-wide text-red-600">
                    <AlertTriangle className="h-3.5 w-3.5" /> Hata
                  </div>
                  <p className="whitespace-pre-wrap rounded-xl bg-red-50 p-3 text-[12px] text-red-700">{d.error}</p>
                </section>
              )}
              {d.sql && (
                <section>
                  <div className="mb-1 flex items-center justify-between">
                    <span className="text-[11px] font-bold uppercase tracking-wide text-canvas-muted">Üretilen SQL</span>
                    <CopyBtn text={d.sql} />
                  </div>
                  <pre className="overflow-x-auto rounded-xl bg-canvas-ink p-3 text-[11.5px] leading-relaxed text-slate-100">{d.sql}</pre>
                </section>
              )}
              {d.result && (
                <section>
                  <div className="mb-1 text-[11px] font-bold uppercase tracking-wide text-canvas-muted">Sonuç</div>
                  <ResultTable result={d.result} />
                </section>
              )}
              {d.gate && Object.keys(d.gate).length > 0 && (
                <section>
                  <div className="mb-1 text-[11px] font-bold uppercase tracking-wide text-canvas-muted">Kapı kararları</div>
                  <pre className="overflow-x-auto rounded-xl bg-amber-50 p-3 text-[11.5px] text-amber-900">{JSON.stringify(d.gate, null, 2)}</pre>
                </section>
              )}
              <details>
                <summary className="cursor-pointer text-[11px] font-bold uppercase tracking-wide text-canvas-muted">Semantik çözümleme</summary>
                <pre className="mt-1 max-h-72 overflow-auto rounded-xl bg-slate-50 p-3 text-[11px] leading-relaxed">{JSON.stringify(d.resolved, null, 2)}</pre>
              </details>
            </>
          )}
        </div>

        {d && (
          <div className="border-t border-slate-100 px-4 py-3 sm:px-6">
            <div className="mb-2 flex flex-wrap gap-1.5">
              {(['todo', 'fixed', 'ignored'] as const).map((f) => (
                <button
                  key={f}
                  type="button"
                  disabled={mark.isPending}
                  onClick={() => mark.mutate({ flag: d.reviewFlag === f ? '' : f, note })}
                  className={[
                    'inline-flex min-h-9 items-center gap-1 rounded-xl px-3 py-1.5 text-[12px] font-bold transition-colors',
                    d.reviewFlag === f ? 'bg-canvas-violet text-white' : 'bg-slate-100 text-canvas-ink hover:bg-slate-200',
                  ].join(' ')}
                >
                  {FLAG[f].label}
                </button>
              ))}
            </div>
            <div className="flex gap-2">
              <input
                value={note}
                onChange={(e) => setNote(e.target.value)}
                placeholder="İnceleme notu (nereyi düzeltelim?)"
                className={field}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') mark.mutate({ note });
                }}
              />
              <button type="button" disabled={mark.isPending || note === (d.reviewNote ?? '')} onClick={() => mark.mutate({ note })} className={btnGhost}>
                Kaydet
              </button>
            </div>
            {d.reviewedBy && <p className="mt-1 text-[11px] text-canvas-muted">Son inceleyen: {d.reviewedBy} · {fmtDate(d.reviewedAt)}</p>}
          </div>
        )}
      </div>
    </div>
  );
}

function Row({ item, onOpen }: { item: PromptRow; onOpen: () => void }) {
  const t = typeInfo(item.answerType);
  return (
    <li>
      <button type="button" onClick={onOpen} className="flex w-full items-start gap-3 py-2.5 text-left hover:bg-slate-50/60">
        <span className="w-24 shrink-0 pt-0.5 text-[11px] tabular-nums text-canvas-muted">{fmtDate(item.createdAt)}</span>
        <span className="min-w-0 flex-1">
          <span className="flex flex-wrap items-center gap-1.5">
            <Pill tone={t.tone}>{t.label}</Pill>
            {item.reviewFlag && <Pill tone={FLAG[item.reviewFlag].tone}>{FLAG[item.reviewFlag].label}</Pill>}
            <span className="text-[11px] font-semibold text-canvas-muted">{item.username ?? 'oturumsuz'}</span>
            {item.rowCount != null && <span className="text-[11px] tabular-nums text-canvas-muted">{nf.format(item.rowCount)} satır</span>}
            {item.latencyMs != null && <span className="text-[11px] tabular-nums text-canvas-muted">{nf.format(item.latencyMs)} ms</span>}
          </span>
          <span className="mt-0.5 block truncate text-[12.5px] font-semibold">{item.question}</span>
          {item.error && <span className="mt-0.5 block truncate text-[11.5px] text-red-600">{item.error}</span>}
        </span>
      </button>
    </li>
  );
}

export default function PromptTracker() {
  const [only, setOnly] = useState('');
  const [days, setDays] = useState('30');
  const [text, setText] = useState('');
  const [search, setSearch] = useState('');
  const [openId, setOpenId] = useState<string | null>(null);

  const daysNum = days ? Number(days) : undefined;
  const overview = useQuery({
    queryKey: ['admin', 'prompts', 'overview', days],
    queryFn: () => adminApi.promptsOverview(daysNum ?? 365),
    retry: false,
    refetchInterval: 60_000,
  });
  const list = useInfiniteQuery({
    queryKey: ['admin', 'prompts', only, search, days],
    queryFn: ({ pageParam }) =>
      adminApi.prompts({ only, q: search, days: daysNum, offset: pageParam ?? 0, limit: 60 }),
    initialPageParam: 0 as number,
    getNextPageParam: (last) => last.nextOffset ?? undefined,
    retry: false,
  });
  const items = list.data?.pages.flatMap((p) => p.items) ?? [];
  const o = overview.data;

  const csv = () => {
    const a = document.createElement('a');
    a.href = adminApi.promptsExportUrl({ only, q: search, days: daysNum });
    a.click();
  };

  return (
    <Section
      title="Promt izleme"
      help="Müşteri ortamında sorulan her soru, üretilen SQL, sonuç ve kapının kararı. Satıra dokunun; incelemek ve nereyi düzelteceğimizi işaretlemek için."
      action={
        <button type="button" onClick={csv} className={btnGhost}>
          <FileDown className="h-4 w-4" /> CSV
        </button>
      }
    >
      {o && (
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
          <Stat label={`Toplam (${o.sinceDays} gün)`} value={o.total} tone="ink" />
          <Stat label="Cevaplanan" value={o.answered} tone="ok" />
          <Stat label="Başarısız" value={o.failed} tone="err" />
          <Stat label="Düzeltilecek" value={o.todo} tone="violet" />
        </div>
      )}

      <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
        <form
          className="relative flex-1"
          onSubmit={(e) => {
            e.preventDefault();
            setSearch(text.trim());
          }}
        >
          <Search className="pointer-events-none absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-canvas-muted" />
          <input value={text} onChange={(e) => setText(e.target.value)} onBlur={() => setSearch(text.trim())} placeholder="Soru ya da SQL ara…" className={`${field} pl-8`} />
        </form>
        <select value={only} onChange={(e) => setOnly(e.target.value)} className={`${field} sm:w-44`} aria-label="Süzgeç">
          {FILTERS.map(([v, l]) => (
            <option key={v} value={v}>
              {l}
            </option>
          ))}
        </select>
        <select value={days} onChange={(e) => setDays(e.target.value)} className={`${field} sm:w-32`} aria-label="Süre">
          {DAYS.map(([v, l]) => (
            <option key={v} value={v}>
              {l}
            </option>
          ))}
        </select>
      </div>

      {o && o.topFailing.length > 0 && (
        <div className="rounded-2xl border border-amber-100 bg-amber-50/60 p-3">
          <div className="mb-1 flex items-center gap-1 text-[11px] font-bold uppercase tracking-wide text-amber-800">
            <AlertTriangle className="h-3.5 w-3.5" /> En sık başarısız sorular
          </div>
          <ul className="flex flex-wrap gap-1.5">
            {o.topFailing.slice(0, 8).map((f) => (
              <li key={f.question}>
                <button
                  type="button"
                  onClick={() => {
                    setText(f.question);
                    setSearch(f.question);
                  }}
                  className="rounded-lg bg-white/80 px-2 py-1 text-[11.5px] font-semibold hover:bg-white"
                >
                  {f.question.length > 48 ? `${f.question.slice(0, 48)}…` : f.question}
                  <span className="ml-1 tabular-nums text-amber-700">×{f.count}</span>
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}

      {list.isLoading ? (
        <Loading />
      ) : list.error ? (
        <Note tone="err">{errText(list.error, 'Promtlar okunamadı.')}</Note>
      ) : items.length ? (
        <div className="rounded-2xl border border-slate-100 bg-white/80 px-4">
          <ul className="divide-y divide-slate-100">
            {items.map((it) => (
              <Row key={it.id} item={it} onOpen={() => setOpenId(it.id)} />
            ))}
          </ul>
        </div>
      ) : (
        <Note tone="info">Bu süzgece uyan promt yok.</Note>
      )}
      {list.hasNextPage && (
        <button type="button" onClick={() => list.fetchNextPage()} disabled={list.isFetchingNextPage} className={btnGhost}>
          <Download className="h-4 w-4" /> {list.isFetchingNextPage ? 'Yükleniyor…' : 'Daha fazla'}
        </button>
      )}

      {openId && <Detail id={openId} onClose={() => setOpenId(null)} />}
    </Section>
  );
}
