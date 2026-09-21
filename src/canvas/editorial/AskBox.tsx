import { Fragment, useEffect, useRef, useState, type ReactNode } from 'react';
import { useMutation, useQuery, useQueries } from '@tanstack/react-query';
import { ArrowUp, BookOpen, Loader2, RotateCcw, Search } from 'lucide-react';
import { ENGINE_ENABLED, bookAskApi, readableBooksApi, type BookQuestion } from '../engine';
import { Note, errText, nf } from '../admin/ui';
import { dateTime } from '../format';
import BookCard from './BookCard';

/** ZEKİ AI'ya kitap sorusu: sohbet görünümü. Cevap kitabın kendi metninden gelir, sayfa numarasıyla;
 *  Soru sunucuda kayıtlı kalır; ekranda yalnız bu açılışta gönderilen sorular gösterilir.
 *  Ekranda iç bileşen/model adı hiçbir yerde geçmez: kullanıcı yalnız ZEKİ AI'yı görür. */

const PRODUCT = 'ZEKİ AI';
const UNAVAILABLE = `${PRODUCT} şu an bu soruyu cevaplayamadı. Birazdan tekrar sorun.`;
const INTERNAL = /\b(?:hermes(?:\s+agent)?|book[-_ ]?director|qwen[\w.-]*|vllm|llama[\w.-]*|gpt[\w.-]*|claude|openai|ocr|editör motoru|editor motoru|dil modeli|llm)\b/gi;

/** Eski kayıtlar ve beklenmedik metinler için ikinci kat: iç adlar ZEKİ AI olur. */
function scrub(s: string): string {
  return s.replace(INTERNAL, PRODUCT).replace(new RegExp(`(?:${PRODUCT}(?:[\\s,/]+|\\s+ve\\s+))+${PRODUCT}`, 'g'), PRODUCT);
}

/** Hata metni teknik ayrıntı taşıyorsa (durum kodu, iç ad) yerine sade cümle gösterilir. */
function friendlyError(e: string): string {
  INTERNAL.lastIndex = 0;
  return INTERNAL.test(e) || /\b\d{3}:|motor/i.test(e) ? UNAVAILABLE : e;
}

const THINKING = ['Sorunuz işleniyor'];
const QUEUED = ['ZEKİ AI sıradaki soruyu bitiriyor', 'Birazdan sizin sorunuza geçecek'];

const SUGGEST = ['hangi karakterler var?', 'hikâye nasıl başlıyor?', 'ana temalar neler?', 'önemli olaylar hangi sayfalarda?'];

/** Sayfa atıflarını («s. 14», «[s.2]») küçük rozetlere çevirir. */
function withPages(text: string): ReactNode[] {
  return text.split(/(\[?s\.\s?\d+(?:\s?[-–]\s?\d+)?\]?)/g).map((part, i) =>
    /^\[?s\.\s?\d/.test(part) ? (
      <span key={i} className="mx-0.5 inline-flex items-center rounded-md bg-canvas-violet/10 px-1.5 py-px align-[1px] font-mono text-[11px] font-bold text-canvas-violet">
        {part.replace(/[[\]]/g, '')}
      </span>
    ) : (
      <Fragment key={i}>{part}</Fragment>
    ),
  );
}

function Orb({ size = 'sm' }: { size?: 'sm' | 'lg' }) {
  const box = size === 'lg' ? 'h-16 w-16' : 'h-8 w-8';
  const inner = size === 'lg' ? 'inset-[3px] text-[15px]' : 'inset-[2px] text-[9px]';
  return (
    <span aria-hidden className={`relative inline-block shrink-0 overflow-hidden rounded-full ${box}`}>
      <span className="zk-orb absolute inset-0" />
      <span className={`absolute ${inner} flex items-center justify-center rounded-full bg-[#15112b] font-extrabold tracking-tight text-white`}>
        Z
      </span>
    </span>
  );
}

function Rotating({ lines }: { lines: string[] }) {
  const [i, setI] = useState(0);
  useEffect(() => {
    const t = window.setInterval(() => setI((n) => (n + 1) % lines.length), 2600);
    return () => window.clearInterval(t);
  }, [lines.length]);
  return (
    <span key={i} className="zk-fade">
      {lines[i % lines.length]}
    </span>
  );
}

function Thinking({ queued }: { queued: boolean }) {
  return (
    <div className="flex items-center gap-2.5 text-[13px] font-semibold text-canvas-ink">
      <span className="flex items-center gap-1" aria-hidden>
        <span className="zk-dot h-1.5 w-1.5 rounded-full bg-canvas-violet" />
        <span className="zk-dot h-1.5 w-1.5 rounded-full bg-canvas-violet [animation-delay:160ms]" />
        <span className="zk-dot h-1.5 w-1.5 rounded-full bg-canvas-violet [animation-delay:320ms]" />
      </span>
      <span className="zk-shimmer" role="status">
        <Rotating lines={queued ? QUEUED : THINKING} />…
      </span>
    </div>
  );
}

function UserBubble({ text, meta }: { text: string; meta?: string }) {
  return (
    <div className="zk-msg flex justify-end">
      <div className="max-w-[85%] sm:max-w-[75%]">
        <div className="whitespace-pre-line break-words rounded-[20px] rounded-br-md bg-gradient-to-br from-canvas-coral via-[#c55cf0] to-canvas-violet px-4 py-2.5 text-[14px] font-medium leading-relaxed text-white shadow-[0_10px_28px_-12px_rgba(124,92,255,.6)]">
          {text}
        </div>
        {meta && <div className="mt-1 pr-1 text-right text-[10.5px] text-canvas-muted">{meta}</div>}
      </div>
    </div>
  );
}

function AiBubble({ children, meta }: { children: ReactNode; meta?: string }) {
  return (
    <div className="zk-msg flex items-end gap-2.5">
      <span className="hidden sm:contents"><Orb /></span>
      <div className="min-w-0 w-full sm:w-auto sm:max-w-[80%]">
        <div className="rounded-[20px] rounded-bl-md border border-white/80 bg-white/90 px-2 py-3 text-[14px] leading-relaxed text-canvas-ink shadow-[0_8px_30px_-14px_rgba(20,30,60,.25)] backdrop-blur sm:px-4">
          {children}
        </div>
        {meta && <div className="mt-1 pl-1 text-[10.5px] text-canvas-muted">{meta}</div>}
      </div>
    </div>
  );
}

function Turn({ q, onRetry, onPickBook }: { q: BookQuestion; onRetry: (text: string) => void; onPickBook: (title: string) => void }) {
  const live = q.status === 'bekliyor' || q.status === 'calisiyor';
  const answer = q.answer ? scrub(q.answer) : null;
  return (
    <div className="space-y-3">
      <UserBubble text={q.question} meta={[q.bookTitle && `«${q.bookTitle}»`, dateTime(q.createdAt)].filter(Boolean).join(' · ')} />
      {live && (
        <AiBubble>
          <Thinking queued={q.status === 'bekliyor'} />
          <p className="mt-1.5 text-[11.5px] leading-snug text-canvas-muted">Cevap birkaç dakika sürebilir. Yanıtı burada bekleyebilirsiniz.</p>
        </AiBubble>
      )}
      {answer && q.notFound && (
        <AiBubble meta={q.elapsedMs ? `${nf.format(Math.round(q.elapsedMs / 1000))} sn'de cevapladı` : undefined}>
          <div className="flex gap-2.5">
            <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-amber-100 text-amber-700">
              <Search aria-hidden className="h-3.5 w-3.5" />
            </span>
            <p className="whitespace-pre-line text-amber-950">{withPages(answer)}</p>
          </div>
        </AiBubble>
      )}
      {answer && !q.notFound && (
        <AiBubble meta={q.elapsedMs ? `${nf.format(Math.round(q.elapsedMs / 1000))} sn'de cevapladı` : undefined}>
          <p className="whitespace-pre-line break-words">{withPages(answer)}</p>
          {q.cards?.map((card) => <BookCard key={card.id} card={card} onAsk={() => onPickBook(card.title)} />)}
          {q.cardError && <p role="status" className="mt-2 text-sm text-amber-800">{q.cardError}</p>}
        </AiBubble>
      )}
      {!live && !answer && (
        <AiBubble>
          <p className="text-red-700">{friendlyError(q.error ? scrub(q.error) : UNAVAILABLE)}</p>
          <button
            type="button"
            onClick={() => onRetry(q.question)}
            className="zk-press mt-2 inline-flex min-h-9 items-center gap-1.5 rounded-lg bg-slate-100 px-3 text-[12px] font-bold text-canvas-ink hover:bg-slate-200"
          >
            <RotateCcw aria-hidden className="h-3.5 w-3.5" />
            Tekrar sor
          </button>
        </AiBubble>
      )}
    </div>
  );
}

export default function AskBox({ bookKey, bookTitle }: { bookKey?: string; bookTitle?: string }) {
  const [text, setText] = useState('');
  const [picked, setPicked] = useState<string | null>(null);
  const input = useRef<HTMLTextAreaElement>(null);
  const scroller = useRef<HTMLDivElement>(null);
  // Only IDs created in this mounted conversation are shown. A refresh starts empty.
  const [questionIds, setQuestionIds] = useState<string[]>([]);
  const questions = useQueries({
    queries: questionIds.map((id) => ({
      queryKey: ['editorial', 'question', id],
      queryFn: () => bookAskApi.one(id),
      enabled: ENGINE_ENABLED,
      refetchInterval: (query: { state: { data?: BookQuestion } }) =>
        !query.state.data || ['bekliyor', 'calisiyor'].includes(query.state.data.status) ? 5000 : false,
    })),
  });
  const ask = useMutation({
    mutationFn: (question: string) => bookAskApi.ask({ question, bookKey, bookTitle: bookTitle ?? picked ?? undefined }),
    onSuccess: (result) => setQuestionIds((ids) => [...ids, result.id]),
  });
  // Sayfa bir kitaba bağlı değilse okunmuş kitaplar gösterilir; kişi birini seçerek soruyu ona yöneltir.
  const books = useQuery({
    queryKey: ['editorial', 'readableBooks'],
    queryFn: readableBooksApi.list,
    enabled: ENGINE_ENABLED,
    staleTime: 5 * 60_000,
    refetchInterval: (query) => (query.state.data?.loading ? 15000 : 5 * 60_000),
  });
  const readable = books.data?.items ?? [];
  // Sohbet sırası: eski üstte, yeni altta.
  const turns = questions.flatMap((query) => query.data ? [query.data] : []);
  const err = ask.error ? friendlyError(scrub(errText(ask.error, 'Soru gönderilemedi.') ?? '')) : questions.some((query) => query.error) ? 'Yanıt alınamadı; bağlantı yeniden denenecek.' : null;
  const off = !ENGINE_ENABLED || books.data?.configured === false;
  const pending = ask.isPending ? ask.variables : null;
  const target = bookTitle ?? picked;

  const send = (value = text) => {
    const v = value.trim();
    if (!v || ask.isPending || off) return;
    setText('');
    ask.mutate(v, { onError: () => setText(v) });
  };

  // Yeni mesaj gelince ya da durum değişince sohbet en alta kayar.
  const last = turns[turns.length - 1];
  const tick = `${turns.length}-${last?.id}-${last?.status}-${pending ?? ''}`;
  useEffect(() => {
    const el = scroller.current;
    if (el) el.scrollTo({ top: turns.length || pending ? el.scrollHeight : 0 });
  }, [tick]);

  // İçeriğe göre büyüyen giriş alanı (en fazla ~6 satır).
  useEffect(() => {
    const el = input.current;
    if (!el) return;
    el.style.height = 'auto';
    el.style.height = `${Math.min(el.scrollHeight, 168)}px`;
  }, [text]);

  const empty = !questionIds.length && !pending;

  return (
    <section className="zk-frame relative overflow-hidden rounded-[28px] p-[1.5px] shadow-[0_30px_80px_-30px_rgba(124,92,255,.45)]">
      <div className={`relative flex flex-col rounded-[26.5px] bg-[#fbfaff] ${empty ? '' : 'h-[min(680px,80dvh)] min-h-[280px]'}`}>
        <div aria-hidden className="zk-aurora pointer-events-none absolute inset-x-0 top-0 h-56" />

        <header className="relative flex shrink-0 items-center gap-3 border-b border-white/70 px-4 py-3.5 sm:px-6">
          <Orb />
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2">
              <h2 className="bg-gradient-to-r from-canvas-coral to-canvas-violet bg-clip-text text-[17px] font-extrabold tracking-tight text-transparent">ZEKİ AI</h2>
              <span className="rounded-full bg-white/80 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide text-canvas-violet">Kitaba sor</span>
            </div>
            <p className="truncate text-[11.5px] text-canvas-muted">{target ? `«${target}» kitabıyla konuşuyorsunuz` : 'Okunmuş kitapların içini bilen asistanınız'}</p>
          </div>
          <span className={`hidden items-center gap-1.5 text-[11px] font-semibold sm:flex ${off ? 'text-amber-700' : 'text-emerald-700'}`}>
            <span className={`h-2 w-2 rounded-full ${off ? 'bg-amber-500' : 'bg-emerald-500 shadow-[0_0_0_3px_rgba(16,185,129,.18)]'}`} />
            {off ? 'Kapalı' : 'Sohbet'}
          </span>
        </header>

        <div ref={scroller} className={`zk-scroll relative min-h-0 space-y-5 px-3 py-4 sm:px-6 ${empty ? '' : 'flex-1 overflow-y-auto overscroll-contain'}`}>
          {off && <Note tone="warn">{PRODUCT} bu kurulumda tanımlı değil; kitap içeriğine soru sorulamaz.</Note>}
          {empty && !off && (
            <div className="zk-msg flex flex-col items-center py-2 text-center">
              <h3 className="text-[20px] font-extrabold tracking-tight text-canvas-ink sm:text-[26px]">
                Merhaba, ben{' '}
                <span className="bg-gradient-to-r from-canvas-coral via-[#c55cf0] to-canvas-violet bg-clip-text text-transparent">ZEKİ AI</span>
              </h3>
              <p className="mt-1.5 max-w-[46ch] text-[13px] leading-relaxed text-canvas-muted">
                Okuduğumuz kitaplara soru sorun. Cevapta kitap adını ve kaynak sayfasını görün; tek bir kitabı seçerek de devam edebilirsiniz.
              </p>
              <div className="mt-4 flex max-w-[620px] flex-wrap justify-center gap-2">
                {SUGGEST.map((s) => {
                  const question = target ? `«${target}» kitabında ${s}` : `Okuduğumuz kitaplarda ${s}`;
                  return (
                  <button
                    key={s}
                    type="button"
                    onClick={() => {
                      setText(question);
                      input.current?.focus();
                    }}
                    className="zk-press rounded-full border border-canvas-violet/15 bg-white/90 px-3.5 py-2 text-[12.5px] font-semibold text-canvas-ink shadow-sm hover:border-canvas-violet/40 hover:text-canvas-violet"
                  >
                    {question}
                  </button>
                ); })}
              </div>
            </div>
          )}
          {turns.map((q) => (
            <Turn key={q.id} q={q} onRetry={(t) => send(t)} onPickBook={(title) => { setPicked(title); setText(`«${title}» kitabı hakkında `); input.current?.focus(); }} />
          ))}
          {questions.some((query) => query.isPending) && <p role="status" className="text-sm text-canvas-muted">Soru kaydı alınıyor…</p>}
          {pending && (
            <div className="space-y-3">
              <UserBubble text={pending} />
              <AiBubble>
                <Thinking queued={false} />
              </AiBubble>
            </div>
          )}
        </div>

        <div className="sticky bottom-0 z-10 shrink-0 border-t border-white/70 bg-white/95 px-3 pb-3 pt-2.5 backdrop-blur sm:px-5 sm:pb-4">
          {!bookTitle && readable.length > 0 && (
            <div className="zk-scroll mb-2 flex items-center gap-1.5 overflow-x-auto pb-0.5">
              <BookOpen aria-hidden className="h-3.5 w-3.5 shrink-0 text-canvas-muted" />
              {readable.map((t) => (
                <button
                  key={t}
                  type="button"
                  onClick={() => setPicked(picked === t ? null : t)}
                  aria-pressed={picked === t}
                  className={`zk-press shrink-0 min-h-11 max-w-full whitespace-normal rounded-full px-3 py-1 text-[11.5px] font-semibold ${
                    picked === t ? 'bg-canvas-violet text-white shadow-sm' : 'bg-white text-canvas-ink ring-1 ring-slate-200 hover:ring-canvas-violet/40'
                  }`}
                >
                  {t}
                </button>
              ))}
            </div>
          )}
          {!bookTitle && books.data?.loading && !readable.length && (
            <p className="mb-2 px-1 text-[11px] text-canvas-muted">Okunmuş kitaplar getiriliyor; beklemeden kitap adını sorunuza yazabilirsiniz.</p>
          )}
          {err && (
            <div className="mb-2">
              <Note tone="err">{err}</Note>
            </div>
          )}
          <form
            className="zk-composer flex items-end gap-2 rounded-[22px] border border-slate-200 bg-white p-1.5 pl-4 shadow-[0_6px_24px_-12px_rgba(20,30,60,.25)] transition-[border-color,box-shadow] duration-150"
            onSubmit={(e) => {
              e.preventDefault();
              send();
            }}
          >
            <textarea
              ref={input}
              value={text}
              onChange={(e) => setText(e.target.value)}
              onKeyDown={(e) => {
                // Enter gönderir; Shift+Enter yeni satır. Türkçe klavyede harf birleştirme sürerken gönderilmez.
                if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
                  e.preventDefault();
                  send();
                }
              }}
              maxLength={2000}
              rows={1}
              disabled={off}
              placeholder={target ? `«${target}» kitabına sorun…` : "ZEKİ AI'ya sorun: kim ne yaptı, hangi olay hangi sayfada…"}
              aria-label="ZEKİ AI'ya soru"
              className="zk-scroll max-h-[168px] min-h-[44px] min-w-0 flex-1 resize-none bg-transparent py-2.5 text-base font-medium leading-snug text-canvas-ink outline-none placeholder:text-canvas-muted/70 disabled:opacity-60 sm:text-[14.5px]"
            />
            <button
              type="submit"
              disabled={!text.trim() || ask.isPending || off}
              aria-label="Gönder"
              className="zk-press flex h-11 w-11 shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-canvas-coral to-canvas-violet text-white shadow-[0_8px_20px_-8px_rgba(124,92,255,.8)] disabled:opacity-40"
            >
              {ask.isPending ? <Loader2 aria-hidden className="h-5 w-5 animate-spin" /> : <ArrowUp aria-hidden className="h-5 w-5" strokeWidth={2.5} />}
            </button>
          </form>
          <p className="mt-1.5 px-2 text-[10.5px] text-canvas-muted">
            <span className="hidden sm:inline">Enter ile gönderin, Shift+Enter ile alt satıra geçin. </span>
            Cevaplar kitabın metninden, sayfa numarasıyla gelir.
            Sayfa yenilendiğinde bu sohbet temizlenir.
          </p>
        </div>
      </div>
    </section>
  );
}
