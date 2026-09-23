import { useState } from 'react';
import { Link } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ArrowRight, Loader2, PenLine } from 'lucide-react';
import { bookReviewApi, type BookReviewAction, type BookReviewGroup, type BookReviewItem } from '../engine';
import { Loading, Note, btn, btnGhost, errText, field, label } from '../admin/ui';
import { Panel } from './kit';

/** Analizin kitapta emin olamayıp editöre sorduğu yerler. Her kayıt tek bakışta okunur: soru, kitabın o
 *  sayfadaki kendi cümlesi, sayfanın resmi ve ne yapacağını söyleyen düğmeler. Motorun iç notları, güven
 *  puanları ve İngilizce etiketler sunucuda kalır. Karar veren kişi oturumdaki AD hesabıdır. */

const yes = `${btn} h-9 min-h-0 bg-emerald-600 text-white`;
const no = `${btnGhost} h-9 min-h-0`;

type Decide = (items: string[], choice: BookReviewAction['key'], note?: string) => void;

function Thumb({ bookId, page, open, onToggle }: { bookId: string; page: number; open: boolean; onToggle: () => void }) {
  const [failed, setFailed] = useState(false);
  return (
    <button
      type="button"
      onClick={onToggle}
      aria-expanded={open}
      aria-label={`${page}. sayfayı ${open ? 'küçült' : 'büyüt'}`}
      className="relative block w-16 shrink-0 self-start overflow-hidden rounded-lg border border-slate-200 bg-white sm:w-24"
    >
      {failed ? (
        <span className="flex aspect-[2/3] items-center justify-center text-[11px] text-canvas-muted">s.{page}</span>
      ) : (
        <img
          src={bookReviewApi.pageUrl(bookId, page, 240)}
          alt={`${page}. sayfa`}
          loading="lazy"
          onError={() => setFailed(true)}
          className="block aspect-[2/3] w-full object-cover object-top"
        />
      )}
      <span className="absolute inset-x-0 bottom-0 bg-white/90 py-0.5 text-center text-[10.5px] font-bold text-canvas-ink">
        s.{page}
      </span>
    </button>
  );
}

function PageLarge({ bookId, page, figures }: { bookId: string; page: number; figures: string[] }) {
  return (
    <div className="mt-3 grid gap-3 sm:grid-cols-[minmax(0,1fr)_auto]">
      <img
        src={bookReviewApi.pageUrl(bookId, page, 900)}
        alt={`${page}. sayfanın tamamı`}
        className="w-full rounded-xl border border-slate-200 bg-white"
      />
      {figures.length > 0 && (
        <div className="flex flex-wrap content-start gap-2 sm:w-28 sm:flex-col">
          {figures.map((id) => (
            <img
              key={id}
              src={bookReviewApi.figureUrl(bookId, id)}
              alt="Tespitin dayandığı çizim"
              loading="lazy"
              className="h-24 w-24 rounded-lg border border-slate-200 bg-white object-contain sm:h-28 sm:w-28"
            />
          ))}
        </div>
      )}
    </div>
  );
}

function Item({ bookId, title, it, picked, onPick, decide, busy }: {
  bookId: string; title: string; it: BookReviewItem; picked: boolean; onPick: (() => void) | null;
  decide: Decide; busy: boolean;
}) {
  const [large, setLarge] = useState(false);
  const [fixing, setFixing] = useState(false);
  const [note, setNote] = useState('');
  const page = it.quote?.page ?? it.pages[0];

  return (
    <article className="rounded-2xl border border-slate-100 bg-white/90 p-3">
      <div className="flex gap-3">
        {page ? <Thumb bookId={bookId} page={page} open={large} onToggle={() => setLarge((v) => !v)} /> : null}
        <div className="min-w-0 flex-1">
          <div className="flex items-start gap-2">
            {onPick && (
              <input
                type="checkbox"
                checked={picked}
                onChange={onPick}
                aria-label="Toplu karar için seç"
                className="mt-0.5 h-4 w-4 shrink-0 accent-canvas-violet"
              />
            )}
            <p className="text-[11px] font-bold uppercase tracking-wide text-canvas-muted">
              {it.subject}
              {it.pages.length > 0 && ` · s.${it.pages.join(', ')}`}
              {it.priority === 1 && <span className="ml-2 normal-case tracking-normal text-red-700">Önce bakılmalı</span>}
            </p>
          </div>
          <h4 className="mt-1 text-[14px] font-extrabold leading-snug">{it.question}</h4>
          <p className="mt-1 text-[13px] leading-snug">{it.statement}</p>
          {it.quote && (
            <blockquote className="mt-2 rounded-lg border-l-2 border-canvas-violet/40 bg-slate-50 px-2.5 py-1.5 text-[12.5px] italic leading-snug">
              «{it.quote.text}»
              <span className="ml-1 not-italic text-canvas-muted">— kitapta, s.{it.quote.page}</span>
            </blockquote>
          )}

          {it.link === 'proofing' ? (
            <Link to={`/son-okuma?kitap=${encodeURIComponent(title)}`} className={`${no} mt-2`}>
              Son Okuma ekranında aç <ArrowRight aria-hidden className="h-4 w-4" />
            </Link>
          ) : (
            <div className="mt-2 flex flex-wrap gap-2">
              {it.actions.filter((a) => a.key !== 'fix').map((a) => (
                <button key={a.key} type="button" disabled={busy} onClick={() => decide([it.id], a.key)}
                  className={a.tone === 'primary' ? yes : no}>
                  {a.label}
                </button>
              ))}
              {it.actions.some((a) => a.key === 'fix') && (
                <button type="button" disabled={busy} onClick={() => setFixing((v) => !v)} className={no} aria-expanded={fixing}>
                  <PenLine aria-hidden className="h-4 w-4" />Düzelt
                </button>
              )}
            </div>
          )}

          {fixing && (
            <div className="mt-2 space-y-2">
              <label className={label} htmlFor={`d-${it.id}`}>Doğrusu ne?</label>
              <textarea id={`d-${it.id}`} value={note} onChange={(e) => setNote(e.target.value)} rows={2} className={field}
                placeholder="Kitapta doğrusu nasıl, kısaca yazın. Bu kitabın sonraki okumalarına da taşınır." />
              <button type="button" disabled={busy || !note.trim()} onClick={() => decide([it.id], 'fix', note.trim())} className={yes}>
                {busy ? <Loader2 aria-hidden className="h-4 w-4 animate-spin" /> : <PenLine aria-hidden className="h-4 w-4" />}
                Düzeltmeyi kaydet
              </button>
            </div>
          )}
        </div>
      </div>
      {large && page ? <PageLarge bookId={bookId} page={page} figures={it.figures} /> : null}
    </article>
  );
}

function Group({ bookId, title, g, decide, busy }: { bookId: string; title: string; g: BookReviewGroup; decide: Decide; busy: boolean }) {
  const [picked, setPicked] = useState<Set<string>>(new Set());
  const [confirm, setConfirm] = useState<BookReviewAction | null>(null);
  // Toplu cevap yalnız aynı soruyu soran kayıtlarda anlamlı: düğme adları gruptaki ilk kayıttan.
  const choices = (g.items[0]?.actions ?? []).filter((a) => a.key !== 'fix');
  const all = g.items.every((i) => picked.has(i.id));
  const toggle = (id: string) => setPicked((s) => {
    const n = new Set(s);
    if (!n.delete(id)) n.add(id);
    return n;
  });

  return (
    <section className="space-y-2">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="text-[13.5px] font-extrabold">
          {g.title} <span className="font-bold text-canvas-muted">· {g.items.length}</span>
        </h3>
        {g.bulk && g.items.length > 1 && (
          <button type="button" onClick={() => setPicked(all ? new Set() : new Set(g.items.map((i) => i.id)))}
            className={`${no} h-8 px-2.5 text-[11.5px]`}>
            {all ? 'Seçimi kaldır' : 'Hepsini seç'}
          </button>
        )}
      </div>

      {g.bulk && picked.size > 0 && (
        <div className="sticky bottom-2 z-10 flex flex-wrap items-center gap-2 rounded-xl border border-canvas-violet/20 bg-white/95 p-2 shadow-md">
          {confirm ? (
            <>
              <span className="text-[12.5px] font-bold">{picked.size} kayıt «{confirm.label}» olarak kapanacak.</span>
              <button type="button" disabled={busy} className={yes}
                onClick={() => { decide([...picked], confirm.key); setPicked(new Set()); setConfirm(null); }}>
                {busy && <Loader2 aria-hidden className="h-4 w-4 animate-spin" />}Evet, kapat
              </button>
              <button type="button" className={no} onClick={() => setConfirm(null)}>Vazgeç</button>
            </>
          ) : (
            <>
              <span className="text-[12.5px] font-bold">{picked.size} kayıt seçildi</span>
              {choices.map((a) => (
                <button key={a.key} type="button" disabled={busy} onClick={() => setConfirm(a)}
                  className={a.tone === 'primary' ? yes : no}>
                  Hepsine: {a.label}
                </button>
              ))}
            </>
          )}
        </div>
      )}

      {g.items.map((it) => (
        <Item key={it.id} bookId={bookId} title={title} it={it} busy={busy} decide={decide}
          picked={picked.has(it.id)} onPick={g.bulk ? () => toggle(it.id) : null} />
      ))}
    </section>
  );
}

export default function ReviewPanel({ bookId }: { bookId: string }) {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ['review-queue', bookId], queryFn: () => bookReviewApi.queue(bookId) });
  const [saved, setSaved] = useState<string | null>(null);
  const run = useMutation({
    mutationFn: (v: { items: string[]; choice: BookReviewAction['key']; note?: string }) =>
      bookReviewApi.decide(bookId, v.items, v.choice, v.note),
    onSuccess: (r) => {
      setSaved(r.failed.length
        ? `${r.decided} kayıt kaydedildi, ${r.failed.length} kayıt kaydedilemedi: ${r.failed[0].error}`
        : `${r.decided} kayıt kaydedildi.`);
      qc.invalidateQueries({ queryKey: ['review-queue', bookId] });
    },
  });
  const decide: Decide = (items, choice, note) => { setSaved(null); run.mutate({ items, choice, note }); };
  const err = errText(q.error || run.error, 'İnceleme kayıtları okunamadı.');

  if (q.isLoading) return <Panel><Loading /></Panel>;
  if (!q.data && !err) return null;
  const d = q.data;

  return (
    <Panel>
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="text-[15px] font-extrabold">İnceleme</h2>
        {d && (
          <span className="text-[12px] font-bold text-canvas-muted">
            {d.open} soru bekliyor{d.decided ? ` · ${d.decided} karara bağlandı` : ''}
          </span>
        )}
      </div>
      <p className="mt-1 text-[12.5px] leading-snug text-canvas-muted">
        Okuma bu yerlerde emin olamadı ve size soruyor. Sayfanın küçük resmine dokunursanız sayfa büyür.
        Bunlar cevaplanmadan kitabın okuması yayına kabul edilmez.
      </p>

      {err && <div className="mt-3"><Note tone="err">{err}</Note></div>}
      {saved && <div className="mt-3" role="status"><Note tone={saved.includes('kaydedilemedi') ? 'warn' : 'ok'}>{saved}</Note></div>}
      {d && d.open === 0 && <div className="mt-3"><Note tone="ok">Bu kitapta bekleyen soru yok.</Note></div>}

      <div className="mt-4 space-y-6">
        {d?.groups.map((g) => (
          <Group key={g.type} bookId={bookId} title={d.title} g={g} decide={decide} busy={run.isPending} />
        ))}
      </div>
    </Panel>
  );
}
