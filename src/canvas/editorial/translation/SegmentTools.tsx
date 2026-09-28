import { useMemo, useState } from 'react';
import { useMutation, useQuery } from '@tanstack/react-query';
import { Combine, Loader2, Scissors } from 'lucide-react';
import { ENGINE_ENABLED, translationApi, type SegmentRow } from '../../engine';
import { Note, btn, btnGhost, errText } from '../../admin/ui';

/** Segment birleştir / böl (çeviri kipinde, çevirmen ya da işi yöneten). Cümle bölücü diyaloğu parçalamışsa
 *  («Oh dear! Oh dear! I shall be late!» üç segment) sonrakiyle birleştirilir; bölmediyse ikinci segmentin
 *  başlayacağı sözcük seçilerek bölünür. Paragraf ve başlık sınırı aşılmaz; onaylı segment yeniden incelemeye
 *  düşer. Kayıt sunucuda `no` sırasını bitişik tutar; ekran listeyi yeniler, odak ilk segmentte kalır. */

type Merged = Awaited<ReturnType<typeof translationApi.mergeNext>>;
type Split = Awaited<ReturnType<typeof translationApi.split>>;

/** Cümle sonu (kapanan tırnak/parantez dahil): bu sözcükten sonra bölmek önerilir. */
const SENT_END = /[.!?…:;。！？؟]["'”’»)\]]*$/;
const DIALOGUE = /^[—–\-"“«]/;

export default function SegmentTools({
  row,
  srcDir,
  busy,
  run,
  onMerged,
  onSplit,
}: {
  row: SegmentRow;
  srcDir: string;
  /** Editörde kayıt sürüyor mu. */
  busy: boolean;
  /** Bekleyen taslağı kaydedip işlemi editörün kayıt sırasına koyar; işleme son bilinen `updatedAt` verilir. */
  run: <R>(fn: (updatedAt: string | null) => Promise<R>) => Promise<R>;
  onMerged: (r: Merged) => void;
  onSplit: (r: Split) => void;
}) {
  const nx = useQuery({
    queryKey: ['translation', 'segment', row.id, 'next'],
    queryFn: () => translationApi.segmentNext(row.id),
    enabled: ENGINE_ENABLED && !row.heading,
  });
  const [open, setOpen] = useState(false);
  const [at, setAt] = useState<number | null>(null);

  const merge = useMutation({
    mutationFn: () => {
      const next = nx.data?.next;
      if (!next) throw new Error('Sonraki segment okunamadı.');
      return run((updatedAt) => translationApi.mergeNext(row.id, { nextId: next.id, updatedAt, nextUpdatedAt: next.updatedAt }));
    },
    onSuccess: onMerged,
  });
  const split = useMutation({
    mutationFn: (utf16: number) =>
      // Sunucu Unicode kod noktası sayar; JS dizini UTF-16 birimidir.
      run((updatedAt) => translationApi.split(row.id, { at: Array.from(row.source.slice(0, utf16)).length, source: row.source, updatedAt })),
    onSuccess: (r) => {
      setOpen(false);
      setAt(null);
      onSplit(r);
    },
  });

  const tokens = useMemo(() => Array.from(row.source.matchAll(/\S+/g), (m) => ({ text: m[0], start: m.index ?? 0 })), [row.source]);
  if (row.heading) return null;

  const pending = merge.isPending || split.isPending;
  const approvedWarn = (both: boolean) =>
    row.status === 'onaylandi' || (both && nx.data?.next?.status === 'onaylandi')
      ? window.confirm('Onaylı segmentin onayı kalkar ve yeniden incelemeye düşer. Devam edilsin mi?')
      : true;
  const reason = nx.data && !nx.data.mergeable ? nx.data.reason : null;
  const close = () => {
    setOpen(false);
    setAt(null);
    split.reset();
  };

  return (
    <div className="space-y-1.5">
      <div className="flex flex-wrap items-center gap-1.5">
        <button
          type="button"
          disabled={busy || pending || !nx.data?.mergeable}
          onClick={() => {
            if (approvedWarn(true)) merge.mutate();
          }}
          title={reason ?? 'Aynı paragraftaki sonraki segmentle tek segment yap'}
          className={btnGhost}
        >
          {merge.isPending ? <Loader2 aria-hidden className="h-4 w-4 animate-spin" /> : <Combine aria-hidden className="h-4 w-4" />}
          Sonrakiyle birleştir
        </button>
        <button
          type="button"
          disabled={busy || pending || tokens.length < 2}
          aria-expanded={open}
          onClick={() => (open ? close() : setOpen(true))}
          className={btnGhost}
        >
          <Scissors aria-hidden className="h-4 w-4" />
          Böl
        </button>
        {reason && <span className="text-[11px] leading-snug text-canvas-muted">{reason}</span>}
      </div>
      {merge.error && <Note tone="err">{errText(merge.error, 'Birleştirilemedi.')}</Note>}
      {open && (
        <div
          className="rounded-2xl border border-slate-200 bg-slate-50 p-2.5"
          onKeyDown={(e) => {
            if (e.key === 'Escape') {
              e.stopPropagation();
              close();
            }
          }}
        >
          <p className="text-[12px] font-extrabold">İkinci segment hangi sözcükle başlasın?</p>
          <p className="text-[11px] leading-snug text-canvas-muted">
            Çerçeveli sözcükler cümle sonundan sonra gelir. Çeviri ilk segmentte kalır, ikinci segment boş açılır.
          </p>
          <div dir={srcDir} className="mt-2 flex flex-wrap gap-1" role="group" aria-label="Bölme yeri">
            {tokens.map((t, k) => {
              if (k === 0)
                return (
                  <span key={t.start} className="inline-flex min-h-11 items-center px-1.5 text-[13.5px] sm:min-h-8">
                    {t.text}
                  </span>
                );
              const chosen = at === t.start;
              const suggested = SENT_END.test(tokens[k - 1].text) || DIALOGUE.test(t.text);
              const second = at != null && t.start > at;
              return (
                <button
                  key={t.start}
                  type="button"
                  aria-pressed={chosen}
                  aria-label={`«${t.text}» sözcüğünden önce böl`}
                  onClick={() => setAt(t.start)}
                  className={`inline-flex min-h-11 items-center rounded-lg border px-1.5 text-[13.5px] transition-colors duration-150 sm:min-h-8 ${
                    chosen
                      ? 'border-canvas-violet bg-canvas-violet text-white'
                      : suggested
                        ? 'border-canvas-violet/50 bg-white text-canvas-ink hover:border-canvas-violet'
                        : `border-transparent hover:border-slate-300 ${second ? 'bg-white' : ''}`
                  }`}
                >
                  {t.text}
                </button>
              );
            })}
          </div>
          {at != null && (
            <ol className="mt-2 grid gap-1.5 text-[12.5px] leading-snug sm:grid-cols-2">
              <li className="rounded-xl bg-white px-2.5 py-2">
                <span className="block text-[10.5px] font-bold uppercase text-canvas-muted">1. segment</span>
                <span dir={srcDir}>{row.source.slice(0, at).trim()}</span>
              </li>
              <li className="rounded-xl bg-white px-2.5 py-2">
                <span className="block text-[10.5px] font-bold uppercase text-canvas-muted">2. segment (boş açılır)</span>
                <span dir={srcDir}>{row.source.slice(at).trim()}</span>
              </li>
            </ol>
          )}
          {split.error && (
            <div className="mt-2">
              <Note tone="err">{errText(split.error, 'Bölünemedi.')}</Note>
            </div>
          )}
          <div className="mt-2 flex flex-wrap gap-1.5">
            <button
              type="button"
              disabled={at == null || busy || pending}
              onClick={() => {
                if (at != null && approvedWarn(false)) split.mutate(at);
              }}
              className={`${btn} bg-canvas-violet text-white`}
            >
              {split.isPending ? <Loader2 aria-hidden className="h-4 w-4 animate-spin" /> : <Scissors aria-hidden className="h-4 w-4" />}
              Böl
            </button>
            <button type="button" onClick={close} className={btnGhost}>
              Vazgeç
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
