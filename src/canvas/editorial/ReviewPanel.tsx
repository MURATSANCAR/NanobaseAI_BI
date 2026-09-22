import { useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Check, ChevronDown, Loader2, PenLine, X } from 'lucide-react';
import { bookReviewApi, type BookReviewItem } from '../engine';
import { Loading, Note, Pill, btn, btnGhost, btnPrimary, errText, field, label } from '../admin/ui';
import { Panel } from './kit';

/** Analizin karara bağlayamadığı yerler: faili belli olmayan olay, çizimle çelişen cümle,
 *  hikâye dışı görünen sayfa. Bunlar kapanmadan nesil kabul edilemez. Karar veren kişi
 *  oturumdaki AD hesabıdır — ekran ad sormaz, gönderemez de. */

const TONE: Record<number, 'err' | 'warn' | 'muted'> = { 1: 'err', 2: 'warn', 3: 'muted' };
const PRIORITY = { 1: 'Önce bakılmalı', 2: 'Normal', 3: 'Sonra' } as const;

function pagesOf(it: BookReviewItem): number[] {
  const all = [...(it.source_pages || []), ...(it.pages || [])];
  if (it.page_role_page_no) all.push(it.page_role_page_no);
  return [...new Set(all)].sort((a, b) => a - b);
}

/** Sayfa görüntüsü ancak istenince indirilir: bir kuyrukta yüzlerce sayfa olabilir. */
function PageLook({ bookId, page }: { bookId: string; page: number }) {
  const [open, setOpen] = useState(false);
  const ctx = useQuery({
    queryKey: ['review-page', bookId, page],
    queryFn: () => bookReviewApi.pageContext(bookId, page),
    enabled: open,
  });
  return (
    <div className="mt-2">
      <button type="button" onClick={() => setOpen((v) => !v)} className={`${btnGhost} h-8 min-h-0 px-2.5 text-[11.5px]`}>
        <ChevronDown aria-hidden className={`h-3.5 w-3.5 transition-transform duration-200 ease-out ${open ? 'rotate-180' : ''}`} />
        s.{page} sayfasını göster
      </button>
      {open && (
        <div className="mt-2 grid gap-3 sm:grid-cols-[minmax(0,220px)_minmax(0,1fr)]">
          <img
            src={bookReviewApi.pageUrl(bookId, page)}
            alt={`${page}. sayfanın görüntüsü`}
            loading="lazy"
            className="w-full rounded-xl border border-slate-200 bg-white"
          />
          <div className="min-w-0 space-y-2">
            {ctx.isLoading && <p className="text-[12px] text-canvas-muted">Sayfa okunuyor…</p>}
            {ctx.data?.texts.map((t) => (
              <div key={t.source} className="rounded-xl bg-slate-50 p-2.5">
                <span className="text-[11px] font-bold uppercase tracking-wide text-canvas-muted">
                  {t.source === 'OCR' ? 'OCR okuması' : 'PDF metin katmanı'}
                </span>
                <p className="mt-1 whitespace-pre-wrap text-[12px] leading-snug">{t.text.slice(0, 1200) || '—'}</p>
              </div>
            ))}
            {!!ctx.data?.regions.length && (
              <div className="flex flex-wrap gap-2">
                {ctx.data.regions.map((r) => (
                  <figure key={r.id} className="w-24">
                    <img
                      src={bookReviewApi.figureUrl(bookId, r.id)}
                      alt={r.description || r.label}
                      loading="lazy"
                      className="h-24 w-24 rounded-lg border border-slate-200 object-contain bg-white"
                    />
                    <figcaption className="mt-1 truncate text-[11px] text-canvas-muted" title={r.description || r.label}>
                      {r.label}
                    </figcaption>
                  </figure>
                ))}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

export default function ReviewPanel({ bookId, title }: { bookId: string; title?: string | null }) {
  const qc = useQueryClient();
  const [picked, setPicked] = useState<Set<string>>(new Set());
  const [correcting, setCorrecting] = useState<string | null>(null);
  const [correction, setCorrection] = useState('');

  const q = useQuery({ queryKey: ['review-queue', bookId], queryFn: () => bookReviewApi.queue(bookId) });
  const decide = useMutation({
    mutationFn: (v: { items: string[]; decision: 'approve' | 'reject' | 'correct'; note?: string }) =>
      bookReviewApi.decide(bookId, v.items, v.decision, v.note === undefined ? undefined : { note: v.note }),
    onSuccess: () => {
      setPicked(new Set());
      setCorrecting(null);
      setCorrection('');
      qc.invalidateQueries({ queryKey: ['review-queue', bookId] });
    },
  });

  const groups = useMemo(() => {
    const by = new Map<string, BookReviewItem[]>();
    for (const it of q.data?.items || []) by.set(it.kind, [...(by.get(it.kind) || []), it]);
    return [...by.entries()].sort((a, b) => a[1][0].priority - b[1][0].priority);
  }, [q.data]);

  const err = errText(q.error || decide.error, 'İnceleme kuyruğu okunamadı.');
  const busy = decide.isPending;
  const toggle = (id: string) =>
    setPicked((s) => {
      const next = new Set(s);
      if (!next.delete(id)) next.add(id);
      return next;
    });

  if (q.isLoading) return <Panel><Loading /></Panel>;
  if (!q.data && !err) return null;

  return (
    <Panel>
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="text-[13px] font-extrabold">
          İnceleme{q.data?.open ? ` (${q.data.open})` : ''}
        </h2>
        {q.data && (
          <span className="text-[11.5px] text-canvas-muted">
            {q.data.code_version} · {title || q.data.title}
          </span>
        )}
      </div>
      <p className="mt-1 text-[12px] leading-snug text-canvas-muted">
        Analiz emin olamadığı yerde tahmin etmedi, sordu. Bu kayıtlar karara bağlanmadan kitabın okuması
        yayına kabul edilmez. «Düzelt» dediğiniz şey bu kitabın sonraki okumalarına da taşınır.
      </p>

      {err && <div className="mt-3"><Note tone="err">{err}</Note></div>}

      {q.data && !q.data.items.length && (
        <div className="mt-3"><Note tone="ok">Bekleyen inceleme kaydı yok.</Note></div>
      )}

      {picked.size > 0 && (
        <div className="sticky bottom-2 z-10 mt-3 flex flex-wrap items-center gap-2 rounded-xl border border-canvas-violet/20 bg-white/95 p-2 shadow-md">
          <span className="text-[12px] font-bold">{picked.size} kayıt seçildi</span>
          <button type="button" disabled={busy} onClick={() => decide.mutate({ items: [...picked], decision: 'approve' })} className={`${btnPrimary} h-9 min-h-0`}>
            {busy ? <Loader2 aria-hidden className="h-4 w-4 animate-spin" /> : <Check aria-hidden className="h-4 w-4" />}
            Hepsini onayla
          </button>
          <button type="button" disabled={busy} onClick={() => decide.mutate({ items: [...picked], decision: 'reject' })} className={`${btnGhost} h-9 min-h-0`}>
            <X aria-hidden className="h-4 w-4" />
            Hepsini reddet
          </button>
          <button type="button" disabled={busy} onClick={() => setPicked(new Set())} className={`${btnGhost} h-9 min-h-0`}>
            Seçimi bırak
          </button>
        </div>
      )}

      <div className="mt-3 space-y-4">
        {groups.map(([kind, items]) => (
          <section key={kind} className="space-y-2">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <h3 className="text-[12.5px] font-extrabold">{kind} <span className="text-canvas-muted">· {items.length}</span></h3>
              <button
                type="button"
                onClick={() => setPicked((s) => {
                  const next = new Set(s);
                  const all = items.every((i) => next.has(i.id));
                  for (const i of items) (all ? next.delete(i.id) : next.add(i.id));
                  return next;
                })}
                className={`${btnGhost} h-8 min-h-0 px-2.5 text-[11.5px]`}
              >
                {items.every((i) => picked.has(i.id)) ? 'Seçimi kaldır' : 'Bu türün hepsini seç'}
              </button>
            </div>

            {items.map((it) => (
              <article key={it.id} className="rounded-2xl border border-slate-100 bg-white/85 p-3">
                <div className="flex items-start gap-2">
                  <input
                    type="checkbox"
                    checked={picked.has(it.id)}
                    onChange={() => toggle(it.id)}
                    aria-label="Bu kaydı seç"
                    className="mt-1 h-4 w-4 shrink-0 accent-canvas-violet"
                  />
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-1.5">
                      <Pill tone={TONE[it.priority] || 'muted'}>{PRIORITY[it.priority as 1 | 2 | 3] || 'Normal'}</Pill>
                      {pagesOf(it).map((p) => <Pill key={p} tone="violet">s.{p}</Pill>)}
                    </div>
                    <p className="mt-1.5 text-[12.5px] font-semibold leading-snug">{it.reason}</p>
                    {it.claim && (
                      <p className="mt-1 rounded-lg bg-slate-50 px-2.5 py-1.5 text-[12px] leading-snug">
                        <span className="font-bold">{it.claim_kind}: </span>{it.claim}
                      </p>
                    )}
                    {it.description && (
                      <p className="mt-1 text-[12px] leading-snug text-canvas-muted">{it.description}</p>
                    )}
                    {pagesOf(it).slice(0, 1).map((p) => <PageLook key={p} bookId={bookId} page={p} />)}

                    <div className="mt-2 flex flex-wrap gap-2">
                      <button type="button" disabled={busy} onClick={() => decide.mutate({ items: [it.id], decision: 'approve' })} className={`${btn} h-9 min-h-0 bg-emerald-600 text-white`}>
                        <Check aria-hidden className="h-4 w-4" />Onayla
                      </button>
                      <button type="button" disabled={busy} onClick={() => decide.mutate({ items: [it.id], decision: 'reject' })} className={`${btnGhost} h-9 min-h-0`}>
                        <X aria-hidden className="h-4 w-4" />Reddet
                      </button>
                      <button type="button" disabled={busy} onClick={() => { setCorrecting(correcting === it.id ? null : it.id); setCorrection(''); }} className={`${btnGhost} h-9 min-h-0`}>
                        <PenLine aria-hidden className="h-4 w-4" />Düzelt
                      </button>
                    </div>

                    {correcting === it.id && (
                      <div className="mt-2 space-y-2">
                        <label className={label} htmlFor={`d-${it.id}`}>Doğrusu ne olmalı</label>
                        <textarea
                          id={`d-${it.id}`}
                          value={correction}
                          onChange={(e) => setCorrection(e.target.value)}
                          rows={3}
                          className={field}
                          placeholder="Örn: bu sayfa künye sayfasıdır, hikâyeye dahil değildir."
                        />
                        <button
                          type="button"
                          disabled={busy || !correction.trim()}
                          onClick={() => decide.mutate({ items: [it.id], decision: 'correct', note: correction.trim() })}
                          className={`${btnPrimary} h-9 min-h-0`}
                        >
                          {busy ? <Loader2 aria-hidden className="h-4 w-4 animate-spin" /> : <PenLine aria-hidden className="h-4 w-4" />}
                          Düzeltmeyi kaydet
                        </button>
                      </div>
                    )}
                  </div>
                </div>
              </article>
            ))}
          </section>
        ))}
      </div>
    </Panel>
  );
}
