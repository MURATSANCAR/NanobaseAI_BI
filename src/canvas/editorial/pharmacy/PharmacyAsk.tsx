import { useEffect, useRef, useState } from 'react';
import { useMutation, useQuery } from '@tanstack/react-query';
import { ArrowUp, BookOpen, Loader2, RotateCcw, Search } from 'lucide-react';
import { ENGINE_ENABLED, bookAskApi, type BookQuestion } from '../../engine';
import { errText, nf } from '../../admin/ui';
import { AnswerText, Orb, Thinking, friendlyError, scrub } from '../AskBox';
import { answerSources } from './askSources';

/** Kitap Eczanesi'nin en üstündeki «Zeki'ye sor»: Zeki AI'ın okuyup arşive aldığı bütün kitaplara doğal dilde soru.
 *
 *  Yeni bir soru yolu yoktur: Kitaba sor'un kitap seçilmemiş (kütüphane geneli) sorusudur — `POST /api/v1/editorial/ask`
 *  (kitap adı boş), cevap `GET /api/v1/editorial/ask/{id}` yoklamasıyla gelir. Köprü kitap arayan soruyu kart
 *  seçimiyle, gerisini kayıtlardan tek çağrılık hızlı yolla, o da yetmezse derin okumayla cevaplar. Cevabın
 *  metni ve sayfa rozetleri Kitaba sor'dakiyle aynı bileşendir; altında kaynak kitaplar (sayfalarıyla) durur,
 *  kitaba basınca ekrandaki kitap ayrıntısı açılır. Ekranda yalnız son soru durur (sohbet geçmişi Kitaba sor'dadır). */

const EXAMPLES = ["Osmanlı'da taşra idaresini anlatan kitaplarımız hangileri?", "Gölge Tilki'de ana karakter kim?"];

const seconds = (ms: number | null) => (ms ? `${nf.format(Math.max(1, Math.round(ms / 1000)))} sn'de cevapladı` : null);

function Sources({ q, onPick }: { q: BookQuestion; onPick: (id: string) => void }) {
  const list = answerSources(q);
  if (!list.length) return null;
  return (
    <div className="mt-3 border-t border-slate-100 pt-3">
      <p className="text-[11px] font-bold uppercase tracking-wide text-canvas-muted">Kaynak kitaplar</p>
      <ul className="mt-1.5 flex flex-wrap gap-1.5" aria-label="Kaynak kitaplar">
        {list.map((s) => (
          <li key={s.id} className="min-w-0 max-w-full">
            <button
              type="button"
              onClick={() => onPick(s.id)}
              className="zk-press flex min-h-11 max-w-full items-center gap-2 rounded-xl bg-violet-50 px-3 py-1.5 text-left text-[12.5px] font-bold text-canvas-ink ring-1 ring-canvas-violet/15 hover:ring-canvas-violet/40"
            >
              <BookOpen aria-hidden className="h-4 w-4 shrink-0 text-canvas-violet" />
              <span className="min-w-0 break-words">
                {s.title}
                {s.pages.length > 0 && (
                  <span className="ml-1.5 font-mono text-[11px] font-semibold text-canvas-muted tabular-nums">
                    s. {s.pages.slice(0, 6).join(', ')}
                    {s.pages.length > 6 ? ` +${s.pages.length - 6}` : ''}
                  </span>
                )}
              </span>
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}

function Answer({ q, onPick, onRetry }: { q: BookQuestion; onPick: (id: string) => void; onRetry: () => void }) {
  const live = q.status === 'bekliyor' || q.status === 'calisiyor';
  const answer = q.answer ? scrub(q.answer) : null;
  const meta = seconds(q.elapsedMs);
  if (live) {
    return (
      <div className="zk-msg rounded-2xl border border-slate-200/70 bg-white/95 px-4 py-3.5" aria-live="polite">
        <Thinking queued={q.status === 'bekliyor'} />
        <p className="mt-1.5 text-[11.5px] leading-snug text-canvas-muted">Cevap birkaç dakika sürebilir; burada bekleyebilirsiniz.</p>
      </div>
    );
  }
  if (!answer) {
    // Bitti ama metin yok: hata ya da boş cevap. İkisi de sade cümleyle ve yeniden sorma düğmesiyle.
    const msg = q.status === 'hata' ? friendlyError(q.error ? scrub(q.error) : '') || 'Zeki AI şu an bu soruyu cevaplayamadı.' : 'Zeki AI bu soruya bir cevap bulamadı.';
    return (
      <div className="zk-msg rounded-2xl border border-red-200 bg-red-50/70 px-4 py-3.5" role="alert">
        <p className="text-[13.5px] text-red-800">{msg}</p>
        <button
          type="button"
          onClick={onRetry}
          className="zk-press mt-2 inline-flex min-h-11 items-center gap-1.5 rounded-lg bg-white px-3 text-[12.5px] font-bold text-canvas-ink ring-1 ring-red-200 hover:bg-red-50"
        >
          <RotateCcw aria-hidden className="h-3.5 w-3.5" />
          Tekrar sor
        </button>
      </div>
    );
  }
  if (q.notFound) {
    return (
      <div className="zk-msg rounded-2xl border border-amber-200 bg-amber-50/70 px-4 py-3.5" aria-live="polite">
        <div className="flex gap-2.5">
          <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-amber-100 text-amber-700">
            <Search aria-hidden className="h-3.5 w-3.5" />
          </span>
          <div className="min-w-0 text-[14px] leading-relaxed text-amber-950">
            <p className="font-bold">Okunan kitaplarda cevap bulunamadı</p>
            <div className="mt-1"><AnswerText text={answer} book={q} /></div>
          </div>
        </div>
        {meta && <p className="mt-1.5 text-[10.5px] text-amber-800/70">{meta}</p>}
      </div>
    );
  }
  return (
    <div className="zk-msg rounded-2xl border border-slate-200/70 bg-white/95 px-4 py-4 text-[14.5px] leading-relaxed text-canvas-ink shadow-[0_8px_30px_-14px_rgba(20,30,60,.15)] sm:px-5" aria-live="polite">
      <AnswerText text={answer} book={q} />
      <Sources q={q} onPick={onPick} />
      {meta && <p className="mt-2 text-[10.5px] text-canvas-muted">{meta}</p>}
    </div>
  );
}

export default function PharmacyAsk({ onPickBook }: { onPickBook: (id: string) => void }) {
  const [text, setText] = useState('');
  const [qid, setQid] = useState<string | null>(null);
  const input = useRef<HTMLTextAreaElement>(null);

  const question = useQuery({
    queryKey: ['editorial', 'question', qid],
    queryFn: () => bookAskApi.one(qid as string),
    enabled: ENGINE_ENABLED && !!qid,
    refetchInterval: (s) => (!s.state.data || ['bekliyor', 'calisiyor'].includes(s.state.data.status) ? 5000 : false),
  });
  const ask = useMutation({
    mutationFn: (q: string) => bookAskApi.ask({ question: q }),
    onSuccess: (r) => setQid(r.id),
  });
  const q = question.data;
  const waiting = ask.isPending || (!!qid && (!q || q.status === 'bekliyor' || q.status === 'calisiyor'));
  const off = !ENGINE_ENABLED;

  const send = (value = text) => {
    const v = value.trim();
    if (!v || waiting || off) return;
    setText('');
    ask.mutate(v, { onError: () => setText(v) });
  };

  // İçeriğe göre büyüyen giriş alanı (en fazla ~4 satır).
  useEffect(() => {
    const el = input.current;
    if (!el) return;
    el.style.height = 'auto';
    el.style.height = `${Math.min(el.scrollHeight, 120)}px`;
  }, [text]);

  const asked = ask.isPending ? ask.variables : q?.question ?? null;
  const sendErr = ask.error ? friendlyError(scrub(errText(ask.error, 'Soru gönderilemedi.') ?? '')) : null;

  return (
    <section aria-labelledby="eczane-sor" className="glass-panel min-w-0 rounded-2xl p-3 shadow-glass-float ring-1 ring-canvas-violet/15 sm:rounded-3xl sm:p-4">
      <div className="flex items-center gap-2.5">
        <Orb />
        <div className="min-w-0">
          <h2 id="eczane-sor" className="text-[15px] font-extrabold tracking-tight text-canvas-ink">Zeki'ye sor</h2>
          <p className="text-[11.5px] leading-snug text-canvas-muted">Zeki AI'ın okuduğu kitaplara sorun; cevap kaynak kitap ve sayfasıyla gelir.</p>
        </div>
      </div>

      <form
        className="zk-composer mt-3 flex items-end gap-2 rounded-[18px] border border-slate-200 bg-white p-1.5 pl-3.5 shadow-[0_6px_24px_-12px_rgba(20,30,60,.25)] transition-[border-color,box-shadow] duration-150 focus-within:border-canvas-violet/40"
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
          placeholder={`Örn. ${EXAMPLES[0]}`}
          aria-label="Zeki'ye soru"
          className="max-h-[120px] min-h-[44px] min-w-0 flex-1 resize-none bg-transparent py-2.5 text-base font-medium leading-snug text-canvas-ink outline-none placeholder:text-canvas-muted/70 disabled:opacity-60 sm:text-[14px]"
        />
        <button
          type="submit"
          disabled={!text.trim() || waiting || off}
          aria-label="Gönder"
          className="zk-press flex h-11 w-11 shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-canvas-coral to-canvas-violet text-white shadow-[0_8px_20px_-8px_rgba(124,92,255,.8)] disabled:opacity-40"
        >
          {waiting ? <Loader2 aria-hidden className="h-5 w-5 animate-spin" /> : <ArrowUp aria-hidden className="h-5 w-5" strokeWidth={2.5} />}
        </button>
      </form>

      {!asked && !off && (
        <div className="mt-2 flex flex-wrap gap-1.5" role="group" aria-label="Örnek sorular">
          {EXAMPLES.map((s) => (
            <button
              key={s}
              type="button"
              onClick={() => {
                setText(s);
                input.current?.focus();
              }}
              className="zk-press min-h-11 max-w-full rounded-full bg-white px-3 py-1.5 text-left text-[12px] font-semibold text-canvas-ink ring-1 ring-slate-200 hover:text-canvas-violet hover:ring-canvas-violet/40"
            >
              {s}
            </button>
          ))}
        </div>
      )}

      {sendErr && (
        <p role="alert" className="mt-2 rounded-xl bg-red-50 px-3 py-2 text-[12.5px] text-red-800">{sendErr}</p>
      )}

      {asked && (
        <div className="mt-3 space-y-2">
          <p className="break-words text-[12.5px] text-canvas-muted">
            <span className="font-bold text-canvas-ink">Soru:</span> {asked}
          </p>
          {ask.isPending || !q ? (
            question.error ? (
              <p role="alert" className="rounded-xl bg-red-50 px-3 py-2 text-[12.5px] text-red-800">Cevap alınamadı; bağlantı yeniden denenecek.</p>
            ) : (
              <div className="zk-msg rounded-2xl border border-slate-200/70 bg-white/95 px-4 py-3.5" aria-live="polite">
                <Thinking queued={false} />
              </div>
            )
          ) : (
            <Answer q={q} onPick={onPickBook} onRetry={() => send(q.question)} />
          )}
        </div>
      )}
    </section>
  );
}
