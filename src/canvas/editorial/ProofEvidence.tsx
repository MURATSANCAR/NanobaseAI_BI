import { useEffect, useRef, useState, type CSSProperties } from 'react';
import { createPortal } from 'react-dom';
import { X } from 'lucide-react';
import { bookAskApi, type ProofReasonCode, type ProofVerdict, type ProofingFinding, type ProofingSeverity } from '../engine';
import { Note, Pill, btnGhost, errText, field, nf } from '../admin/ui';
import { dateTime } from '../format';

/** M5 son okuma — kanıt paneli ve karar denetimleri.
 *
 *  Bulgu tek başına bir iddiadır; editör kararı sayfayı görüp verir. Panel, bulgunun sayfasını
 *  (tam boy render, oran korunur) ve `bbox` varsa işaretli yeri gösterir; aynı sayfadaki öbür
 *  bulgular küçük numaralı noktalardır. Karar («Doğru» / «Yanlış alarm» + gerekçe) buradan verilir.
 *
 *  Masaüstünde (≥ 1024) listenin yanında yapışkan sütun; darda alttan açılan kart (body'ye portal:
 *  glass-panel'in backdrop-filter'ı `position: fixed`i kendine bağlar, portal bunu aşar). */

export const SEVERITY: Record<ProofingSeverity, { label: string; tone: 'muted' | 'warn' | 'err' }> = {
  INFO: { label: 'bilgi', tone: 'muted' },
  WARN: { label: 'uyarı', tone: 'warn' },
  ERROR: { label: 'hata', tone: 'err' },
};
export const SEVERITY_ORDER: ProofingSeverity[] = ['ERROR', 'WARN', 'INFO'];

/** Yanlış alarm gerekçeleri; kapalı küme, kart servisindeki CHECK ile aynı sıra. */
export const REASONS: Array<[ProofReasonCode, string]> = [
  ['TEXT_CORRECT', 'Metin zaten doğru'],
  ['INTENDED_STYLE', 'Yazarın tercihi'],
  ['DICTIONARY_GAP', 'Sözlük/kural eksik'],
  ['WRONG_PAGE', 'Kanıt yanlış sayfa'],
  ['EXPLAINED_IN_TEXT', 'Metinde açıklaması var'],
  ['NOT_AN_ISSUE', 'Önemsiz'],
  ['OTHER', 'Diğer'],
];
export const reasonLabel = (code: ProofReasonCode | null) => REASONS.find(([c]) => c === code)?.[1] ?? code ?? '';

export type Decide = (findingId: string, verdict: ProofVerdict, reasonCode?: ProofReasonCode, note?: string) => Promise<unknown>;

/** Listede ve panelde aynı bulguyu tanıyan anahtar; kimlik yoksa denetim+sayfa+sıra. */
export const findingKey = (f: ProofingFinding, i: number) => f.id ?? `${f.check}-${f.page ?? 'x'}-${i}`;

const PAGE_IMAGE_WIDTH = 1200;
/** Sayfa görselinin en fazla boyu (vh). */
const MAX_PAGE_VH = 70;
/** İmleç hover'ı destekliyorsa; dokunmatikte hover artığı kalmasın. */
const hoverable = '[@media(hover:hover)]:hover:bg-slate-200';

/** Yanlış alarm gerekçesi: satır içi, tek satır; kapalı küme + isteğe bağlı not (≤ 500). */
function RejectForm({ onSave, onCancel, busy, initial }: { onSave: (r: ProofReasonCode, note: string) => void; onCancel: () => void; busy: boolean; initial?: { reasonCode: ProofReasonCode | null; note: string | null } }) {
  const [reason, setReason] = useState<ProofReasonCode | ''>(initial?.reasonCode ?? '');
  const [note, setNote] = useState(initial?.note ?? '');
  return (
    <form
      className="mt-2 grid gap-1.5 sm:grid-cols-[minmax(0,180px)_minmax(0,1fr)_auto]"
      onSubmit={(e) => {
        e.preventDefault();
        if (reason && !busy) onSave(reason, note.trim());
      }}
    >
      <select aria-label="Yanlış alarm gerekçesi" value={reason} onChange={(e) => setReason(e.target.value as ProofReasonCode | '')} className={field} disabled={busy} autoFocus>
        <option value="">Gerekçe seçin…</option>
        {REASONS.map(([code, text]) => (
          <option key={code} value={code}>
            {text}
          </option>
        ))}
      </select>
      <input aria-label="Not (isteğe bağlı)" value={note} maxLength={500} onChange={(e) => setNote(e.target.value)} placeholder="Not (isteğe bağlı)" className={field} disabled={busy} />
      <div className="flex gap-1.5">
        <button type="submit" disabled={!reason || busy} className={`${btnGhost} flex-1 sm:flex-none`}>
          Kaydet
        </button>
        <button type="button" onClick={onCancel} disabled={busy} className={`${btnGhost} flex-1 sm:flex-none`}>
          Vazgeç
        </button>
      </div>
    </form>
  );
}

/** «Doğru» / «Yanlış alarm» + gerekçe. Karar bulguya iliştirilir, kitabı değiştirmez; tekrar basmak yeni karar yazar. */
export function DecisionControls({ f, decide, busy }: { f: ProofingFinding; decide: Decide | null; busy: boolean }) {
  const d = f.decision;
  const [rejecting, setRejecting] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  // Başka bulguya geçince açık gerekçe formu ve hata o bulguyla gitsin.
  useEffect(() => {
    setRejecting(false);
    setErr(null);
  }, [f.id, f.check, f.page, f.message]);
  if (!decide || !f.id) return null;
  const run = (verdict: ProofVerdict, reasonCode?: ProofReasonCode, note?: string) => {
    setErr(null);
    decide(f.id as string, verdict, reasonCode, note)
      .then(() => setRejecting(false))
      .catch((e: unknown) => setErr(errText(e, 'Karar kaydedilemedi.')));
  };
  const accepted = d?.verdict === 'ACCEPT';
  const rejected = d?.verdict === 'REJECT';
  return (
    <div>
      <div className="flex flex-wrap items-center gap-1.5">
        <button
          type="button"
          aria-pressed={accepted}
          disabled={busy}
          onClick={() => run('ACCEPT')}
          className={`${btnGhost} px-2.5 ${accepted ? 'bg-canvas-mint/25 text-emerald-700 hover:bg-canvas-mint/25' : ''}`}
        >
          Doğru
        </button>
        <button
          type="button"
          aria-pressed={rejected}
          aria-expanded={rejecting}
          disabled={busy}
          onClick={() => setRejecting((v) => !v)}
          className={`${btnGhost} px-2.5 ${rejected ? 'bg-canvas-coral/20 text-red-700 hover:bg-canvas-coral/20' : ''}`}
        >
          Yanlış alarm
        </button>
        {d && (
          <span className="min-w-0 break-words text-[11px] text-canvas-muted">
            {d.decidedBy} · {dateTime(d.at)}
            {rejected && d.reasonCode ? ` · ${reasonLabel(d.reasonCode)}` : ''}
            {d.note ? ` — ${d.note}` : ''}
          </span>
        )}
      </div>
      {rejecting && (
        <RejectForm busy={busy} initial={rejected ? { reasonCode: d?.reasonCode ?? null, note: d?.note ?? null } : undefined} onSave={(r, note) => run('REJECT', r, note || undefined)} onCancel={() => setRejecting(false)} />
      )}
      {err && (
        <div className="mt-1.5">
          <Note tone="err">{err}</Note>
        </div>
      )}
    </div>
  );
}

const pct = (v: number) => `${v / 10}%`;

/** Sayfa görseli + işaretler. Çerçevenin eni `min(%100, 70vh × oran)`, boyu aspect-ratio'dan: görsel çerçeveyi
 *  tam doldurur, yüzdeler görsele birebir oturur (tarayıcının inline-block/transfer kurallarına bel bağlanmaz).
 *  Vurgu kutusunun dışı kutunun kendi gölgesiyle karartılır (tek eleman, ek katman yok); kutu animasyonsuz. */
function PageImage({ bookId, bookTitle, page, marks, activeKey, onPick }: { bookId: string; bookTitle: string | null; page: number; marks: Array<{ key: string; n: number; f: ProofingFinding }>; activeKey: string | null; onPick: (key: string) => void }) {
  const [ratio, setRatio] = useState<number | null>(null); // en / boy; yüklenene dek A-serisi varsayımı
  const [failed, setFailed] = useState(false);
  const src = bookAskApi.pageImageUrl(bookId, page, PAGE_IMAGE_WIDTH);
  // Sayfa değişince eski görsel yeni sayfaymış gibi durmasın.
  useEffect(() => {
    setRatio(null);
    setFailed(false);
  }, [src]);
  const loaded = ratio !== null;
  const r = ratio ?? 1 / 1.41;
  const active = marks.find((m) => m.key === activeKey);
  const box = active?.f.bbox ?? null;
  const frame: CSSProperties = { width: `min(100%, calc(${MAX_PAGE_VH}vh * ${r.toFixed(4)}))`, aspectRatio: `${r.toFixed(4)}` };

  if (failed) return <p className="rounded-xl bg-slate-50 px-3 py-6 text-center text-[12px] text-canvas-muted">Sayfa görseli yok.</p>;
  return (
    <div className="relative mx-auto overflow-hidden rounded-xl bg-[#f3efff] ring-1 ring-slate-200/70" style={frame}>
      {!loaded && <span aria-hidden className="absolute inset-0 animate-[zkShimmer_1.4s_linear_infinite] bg-[linear-gradient(100deg,#f3efff_30%,#faf8ff_50%,#f3efff_70%)] bg-[length:200%_100%] motion-reduce:animate-none" />}
      <img
        src={src}
        alt={`${bookTitle ? `«${bookTitle}» ` : ''}sayfa ${page}`}
        decoding="async"
        draggable={false}
        onLoad={(e) => {
          const el = e.currentTarget;
          setRatio(el.naturalWidth > 0 && el.naturalHeight > 0 ? el.naturalWidth / el.naturalHeight : 1 / 1.41);
        }}
        onError={() => setFailed(true)}
        className={`absolute inset-0 h-full w-full select-none ${loaded ? 'opacity-100' : 'opacity-0'}`}
      />
      {loaded && box && (
        <div
          aria-hidden
          className="pointer-events-none absolute rounded-[3px] border-2 border-canvas-violet bg-canvas-violet/10 shadow-[0_0_0_9999px_rgba(27,31,42,0.16)]"
          style={{ left: pct(box[0]), top: pct(box[1]), width: pct(Math.max(box[2] - box[0], 4)), height: pct(Math.max(box[3] - box[1], 4)) }}
        />
      )}
      {loaded &&
        marks
          .filter((m) => m.f.bbox && m.key !== activeKey)
          .map((m) => {
            const b = m.f.bbox as [number, number, number, number];
            const style: CSSProperties = { left: pct(b[0]), top: pct(b[1]) };
            return (
              <button
                key={m.key}
                type="button"
                aria-label={`${m.n}. bulgu: ${m.f.message}`}
                title={m.f.message}
                onClick={() => onPick(m.key)}
                style={style}
                className="absolute z-[1] flex h-5 min-w-5 -translate-x-1/2 -translate-y-1/2 items-center justify-center rounded-full bg-white px-1 font-mono text-[10px] font-extrabold tabular-nums text-canvas-violet shadow-md ring-2 ring-canvas-violet transition-transform duration-150 ease-out active:scale-[0.96] [@media(hover:hover)]:hover:scale-110"
              >
                {m.n}
              </button>
            );
          })}
    </div>
  );
}

type PanelProps = {
  bookId: string | null;
  bookTitle: string | null;
  /** Açık sayfa; null ise «kitap geneli» (görsel yok). */
  page: number | null;
  /** Bu sayfadaki bulgular liste sırasıyla; `n` listedeki ve görseldeki numara. */
  marks: Array<{ key: string; n: number; f: ProofingFinding }>;
  activeKey: string | null;
  onPick: (key: string) => void;
  onClose: () => void;
  decide: Decide | null;
  busy: boolean;
};

function EvidenceBody({ bookId, bookTitle, page, marks, activeKey, onPick, onClose, decide, busy, sheet }: PanelProps & { sheet: boolean }) {
  const active = marks.find((m) => m.key === activeKey) ?? marks[0];
  const f = active?.f;
  const sev = f ? SEVERITY[f.severity] ?? SEVERITY.INFO : null;
  return (
    <>
      <div className="flex items-center justify-between gap-2 px-1">
        <div className="flex min-w-0 flex-wrap items-baseline gap-x-1.5">
          <h3 className="text-[13px] font-extrabold">{page === null ? 'Kitap geneli' : `Sayfa ${nf.format(page)}`}</h3>
          <span className="text-[11px] text-canvas-muted">
            {nf.format(marks.length)} bulgu{bookTitle ? ` · ${bookTitle}` : ''}
          </span>
        </div>
        <button type="button" onClick={onClose} aria-label="Kanıtı kapat" className={`${btnGhost} min-h-9 px-2 sm:min-h-9 ${hoverable}`}>
          <X aria-hidden className="h-4 w-4" />
          {!sheet && <kbd className="font-mono text-[10px] font-bold text-canvas-muted">Esc</kbd>}
        </button>
      </div>

      <div className="mt-2">
        {page !== null && bookId ? (
          <PageImage bookId={bookId} bookTitle={bookTitle} page={page} marks={marks} activeKey={active?.key ?? null} onPick={onPick} />
        ) : (
          <p className="rounded-xl bg-slate-50 px-3 py-4 text-center text-[12px] leading-snug text-canvas-muted">
            {page === null ? 'Bu bulgu tek bir sayfaya bağlı değil; kitabın bütününe ilişkindir.' : 'Kitap kimliği yok; sayfa görseli getirilemiyor.'}
          </p>
        )}
      </div>

      {marks.length > 1 && (
        <div className="mt-2 flex flex-wrap gap-1" role="group" aria-label="Bu sayfadaki bulgular">
          {marks.map((m) => {
            const on = m.key === active?.key;
            return (
              <button
                key={m.key}
                type="button"
                aria-pressed={on}
                onClick={() => onPick(m.key)}
                title={m.f.message}
                className={`inline-flex h-7 min-w-7 items-center justify-center rounded-lg px-1.5 font-mono text-[11px] font-extrabold tabular-nums transition-transform duration-150 ease-out active:scale-[0.96] ${
                  on ? 'bg-canvas-violet text-white' : `bg-slate-100 text-canvas-ink ${hoverable}`
                }${m.f.bbox ? '' : ' opacity-70'}`}
              >
                {m.n}
              </button>
            );
          })}
        </div>
      )}

      {f && sev && (
        <div className="mt-3 rounded-xl border border-slate-100 bg-white/85 px-3 py-2.5 text-[12.5px]">
          <div className="flex flex-wrap items-center gap-1.5">
            <span className="font-mono text-[11px] font-extrabold tabular-nums text-canvas-violet">{active.n}</span>
            <Pill tone={sev.tone}>{sev.label}</Pill>
            <span className="min-w-0 break-words text-[11px] text-canvas-muted">{f.label}</span>
            {!f.bbox && page !== null && <span className="text-[10.5px] text-canvas-muted">· yer işareti yok</span>}
          </div>
          {f.quote && <p className="mt-1.5 break-words border-l-2 border-canvas-violet/50 pl-2 text-[13px] leading-snug text-canvas-ink">“{f.quote}”</p>}
          <p className="mt-1.5 break-words font-semibold leading-snug">{f.message}</p>
          {f.suggestion && (
            <p className="mt-1 break-words text-[11.5px] leading-snug text-canvas-muted">
              <span className="font-bold text-canvas-ink">Öneri:</span> {f.suggestion}
            </p>
          )}
          <div className="mt-2.5">
            <DecisionControls f={f} decide={decide} busy={busy} />
          </div>
        </div>
      )}
      {!sheet && (
        <p className="mt-2 px-1 text-[10.5px] text-canvas-muted">
          <kbd className="font-mono font-bold">↑</kbd> <kbd className="font-mono font-bold">↓</kbd> bulgular arasında · <kbd className="font-mono font-bold">Esc</kbd> kapatır
        </p>
      )}
    </>
  );
}

/** Açılışta bir kare sonra görünür: 150 ms ease-out, opacity + 4 px yukarı. Bulgu/sayfa değişince yeniden oynamaz
 *  (okunan veri yerinden oynamaz); reduced-motion'da yalnız opacity. */
function useEntered() {
  const [entered, setEntered] = useState(false);
  useEffect(() => {
    const f = window.requestAnimationFrame(() => setEntered(true));
    return () => window.cancelAnimationFrame(f);
  }, []);
  return entered;
}
const enterCls = (entered: boolean) =>
  `transition-[opacity,transform] duration-150 ease-[cubic-bezier(0.23,1,0.32,1)] motion-reduce:transition-opacity ${entered ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-1 motion-reduce:translate-y-0'}`;

/** Masaüstü: liste yanında yapışkan sütun. */
export function ProofEvidence(props: PanelProps) {
  const entered = useEntered();
  return (
    <aside aria-label="Bulgu kanıtı" className={`rounded-2xl border border-canvas-violet/15 bg-white/70 p-3 lg:sticky lg:top-3 lg:self-start ${enterCls(entered)}`}>
      <EvidenceBody {...props} sheet={false} />
    </aside>
  );
}

/** Dar ekran: alttan açılan kart. Odak karta gelir, kapanınca çağıran geri alır; arkadaki sayfa kaymaz. */
export function ProofEvidenceSheet(props: PanelProps) {
  const entered = useEntered();
  const ref = useRef<HTMLDivElement>(null);
  const { onClose } = props;
  useEffect(() => {
    ref.current?.focus();
    const prev = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      document.body.style.overflow = prev;
    };
  }, []);
  return createPortal(
    <div className={`fixed inset-0 z-50 flex items-end justify-center bg-canvas-ink/40 transition-opacity duration-150 ease-out ${entered ? 'opacity-100' : 'opacity-0'}`} onClick={onClose}>
      <div
        ref={ref}
        role="dialog"
        aria-modal="true"
        aria-label="Bulgu kanıtı"
        tabIndex={-1}
        onClick={(e) => e.stopPropagation()}
        className={`max-h-[92dvh] w-full overflow-y-auto rounded-t-3xl bg-white p-3 pb-[max(12px,env(safe-area-inset-bottom))] shadow-2xl outline-none ${enterCls(entered)}`}
      >
        <span aria-hidden className="mx-auto mb-2 block h-1 w-10 rounded-full bg-slate-200" />
        <EvidenceBody {...props} sheet />
      </div>
    </div>,
    document.body,
  );
}
