import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Loader2, Search, Send, Sparkles } from 'lucide-react';
import { ENGINE_ENABLED, bookAskApi, readableBooksApi, type BookQuestion } from '../engine';
import { Note, Pill, btn, errText, nf } from '../admin/ui';
import { dateTime } from '../format';

/** Kitabın içeriğine soru. Cevap kitabın kendi metninden gelir, sayfa numarasıyla; köprü uydurmaz.
 *  Motor modeli istendiğinde açtığı ve GPU'yu analizle paylaştığı için soru bir iştir: dakikalar sürebilir. */

const STATUS: Record<BookQuestion['status'], { label: string; tone: 'ok' | 'warn' | 'err' | 'muted' }> = {
  bekliyor: { label: 'Sırada', tone: 'muted' },
  calisiyor: { label: 'Motor çalışıyor', tone: 'warn' },
  bitti: { label: 'Cevaplandı', tone: 'ok' },
  hata: { label: 'Cevaplanamadı', tone: 'err' },
};

function Answer({ q }: { q: BookQuestion }) {
  const live = q.status === 'bekliyor' || q.status === 'calisiyor';
  return (
    <li className="rounded-2xl border border-slate-100 bg-white/85 p-3 text-[12.5px]">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="min-w-0 break-words font-semibold leading-snug">{q.question}</span>
        <span className="flex shrink-0 items-center gap-1.5">
          {live && <Loader2 aria-hidden className="h-3.5 w-3.5 animate-spin text-canvas-muted" />}
          <Pill tone={STATUS[q.status].tone}>{STATUS[q.status].label}</Pill>
        </span>
      </div>
      <div className="mt-0.5 text-[11px] text-canvas-muted">
        {[q.bookTitle, dateTime(q.createdAt), q.elapsedMs ? `${nf.format(Math.round(q.elapsedMs / 1000))} sn` : null].filter(Boolean).join(' · ')}
      </div>
      {q.answer && q.notFound && (
        <div className="mt-2 flex gap-2 rounded-xl bg-amber-50/80 px-3 py-2.5">
          <Search aria-hidden className="mt-0.5 h-4 w-4 shrink-0 text-amber-700" />
          <p className="whitespace-pre-line leading-relaxed text-amber-900">{q.answer}</p>
        </div>
      )}
      {q.answer && !q.notFound && <p className="mt-2 whitespace-pre-line leading-relaxed">{q.answer}</p>}
      {q.error && (
        <div className="mt-2">
          <Note tone="err">{q.error}</Note>
        </div>
      )}
      {live && !q.answer && (
        <p className="mt-2 text-[11.5px] leading-snug text-canvas-muted">
          Soru motora iletildi. Motor başka bir kitabı okuyorsa sıraya girer; cevap birkaç dakika sürebilir. Sayfadan ayrılabilirsiniz, soru kayıtlı kalır.
        </p>
      )}
    </li>
  );
}

export default function AskBox({ bookKey, bookTitle }: { bookKey?: string; bookTitle?: string }) {
  const [text, setText] = useState('');
  const [picked, setPicked] = useState<string | null>(null);
  const qc = useQueryClient();
  const list = useQuery({
    queryKey: ['editorial', 'ask', bookKey ?? ''],
    queryFn: () => bookAskApi.list(bookKey),
    enabled: ENGINE_ENABLED,
    // Bekleyen soru varken kendi kendine tazelenir.
    refetchInterval: (query) => (query.state.data?.items.some((i) => i.status === 'bekliyor' || i.status === 'calisiyor') ? 5000 : false),
  });
  const ask = useMutation({
    mutationFn: () => bookAskApi.ask({ question: text.trim(), bookKey, bookTitle: bookTitle ?? picked ?? undefined }),
    onSuccess: async () => {
      setText('');
      await qc.invalidateQueries({ queryKey: ['editorial', 'ask', bookKey ?? ''] });
    },
  });
  // Sayfa bir kitaba bağlı değilse okunmuş kitaplar gösterilir; kişi birini seçerek soruyu ona yöneltir.
  const books = useQuery({
    queryKey: ['editorial', 'readableBooks'],
    queryFn: readableBooksApi.list,
    enabled: ENGINE_ENABLED && !bookTitle,
    // Liste arka planda tazelenir; hazır olana kadar birkaç saniyede bir bakılır.
    // Motor bir kitabı okuyorsa liste sıraya girer; seyrek bakılır, sayfa beklemez.
    refetchInterval: (query) => (query.state.data?.loading ? 15000 : false),
  });
  const readable = books.data?.items ?? [];
  const items = list.data?.items ?? [];
  const err = errText(list.error || ask.error, 'Soru gönderilemedi.');
  const off = list.data && !list.data.configured;

  return (
    <div>
      {off && <Note tone="warn">Editör motoru bu kurulumda tanımlı değil; kitap içeriğine soru sorulamaz.</Note>}
      <form
        className="relative"
        onSubmit={(e) => {
          e.preventDefault();
          if (text.trim() && !ask.isPending && !off) ask.mutate();
        }}
      >
        <Sparkles aria-hidden className="pointer-events-none absolute left-4 top-4 h-5 w-5 text-canvas-violet" />
        <textarea
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') e.currentTarget.form?.requestSubmit();
          }}
          rows={2}
          disabled={off}
          placeholder={bookTitle ? `«${bookTitle}» kitabına sorun: kim ne yaptı, hangi olay hangi sayfada…` : picked ? `«${picked}» kitabına sorun: kim ne yaptı, hangi olay hangi sayfada…` : 'Okunmuş bir kitaba sorun: kim ne yaptı, hangi olay hangi sayfada…'}
          aria-label="Kitabın içeriğine soru"
          className="min-h-[76px] w-full resize-y rounded-2xl border border-slate-200 bg-white/95 py-3.5 pl-12 pr-28 text-[14px] font-medium leading-snug outline-none transition-[border-color,box-shadow] duration-150 placeholder:text-canvas-muted/70 focus:border-canvas-violet focus:shadow-[0_0_0_3px_rgba(124,92,255,.12)] disabled:opacity-60"
        />
        <button
          type="submit"
          disabled={!text.trim() || ask.isPending || off}
          className={`${btn} absolute bottom-3 right-3 bg-gradient-to-r from-canvas-coral to-canvas-violet text-white shadow-md`}
        >
          {ask.isPending ? <Loader2 aria-hidden className="h-4 w-4 animate-spin" /> : <Send aria-hidden className="h-4 w-4" />}
          Sor
        </button>
      </form>
      {!bookTitle && books.data?.loading && !readable.length && (
        <p className="mt-2 px-1 text-[11px] leading-snug text-canvas-muted">
          Okunmuş kitapların listesi hazırlanıyor. Motor şu an bir kitabı okuyorsa liste ve sorular sıraya girer; kitap adını kendiniz de yazabilirsiniz.
        </p>
      )}
      {!bookTitle && readable.length > 0 && (
        <div className="mt-2 flex flex-wrap items-center gap-1.5">
          <span className="text-[11px] font-bold uppercase tracking-wide text-canvas-muted">Okunmuş kitaplar</span>
          {readable.map((t) => (
            <button
              key={t}
              type="button"
              onClick={() => setPicked(picked === t ? null : t)}
              aria-pressed={picked === t}
              className={`min-h-7 rounded-lg px-2 text-[11.5px] font-semibold transition-colors duration-150 ${
                picked === t ? 'bg-canvas-violet text-white' : 'bg-slate-100 text-canvas-ink hover:bg-slate-200'
              }`}
            >
              {t}
            </button>
          ))}
          {picked && <span className="text-[11px] text-canvas-muted">soru «{picked}» kitabına gidecek</span>}
        </div>
      )}
      <p className="mt-1.5 px-1 text-[11px] leading-snug text-canvas-muted">
        Cevap kitabın kendi metninden gelir ve sayfa numarasıyla verilir. Kitapta olmayan bir şey uydurulmaz.
        {list.data?.running ? ` Şu an ${nf.format(list.data.running)} soru sırada.` : ''}
      </p>

      {err && (
        <div className="mt-2">
          <Note tone="err">{err}</Note>
        </div>
      )}
      {items.length > 0 && (
        <ul className="mt-3 space-y-2">
          {items.map((q) => (
            <Answer key={q.id} q={q} />
          ))}
        </ul>
      )}
    </div>
  );
}
