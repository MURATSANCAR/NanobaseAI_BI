import { useEffect, useMemo, useState } from 'react';
import { Dialog } from '@base-ui/react/dialog';
import { Check, Copy, CornerDownRight, Database, Info, Sigma, X } from 'lucide-react';
import { useCan } from '../useAdmin';
import { allSqlText, collect, copyText, fmtMs, fmtWhen, resolveRef, type KaynakSorgu, type Kaynaklar } from './sqlInfo';

/**
 * Sorgu bilgisi düğmesi: bir rakamın, kartın ya da tablo başlığının yanında küçük «i». Açılan pencerede rakamı üreten
 * hesap (formül), çalıştırılan SQL'in tamamı (kopyalanabilir), bağlantı, veri sonu, satır ve süre. Telefonda alttan
 * açılan sayfa. SQL metni «SQL'i göster ve kopyala» rolünde (`kart.sql-goster`) görünür; formül herkese.
 *
 *   <SqlInfo k={data.kaynaklar} alan="sirket" label="Şirket satışı" />
 *   <SqlInfo k={data.kaynaklar} alan="cards[]" row={card.id} label={card.label} />
 */
export default function SqlInfo({
  k,
  alan,
  row,
  label,
  className = '',
}: {
  k: Kaynaklar | null | undefined;
  alan: string;
  row?: string | number | null;
  label: string;
  className?: string;
}) {
  const [open, setOpen] = useState(false);
  const ref = useMemo(() => resolveRef(k, alan, row), [k, alan, row]);
  if (!k) return null;
  if (!ref && !k.error) {
    if (import.meta.env.DEV) console.warn(`[sorgu bilgisi] kaynağı yazılmamış alan: ${alan}${row != null ? `:${row}` : ''}`);
    return null;
  }
  return (
    <Dialog.Root open={open} onOpenChange={setOpen}>
      <Dialog.Trigger
        className={`relative inline-flex h-5 w-5 shrink-0 items-center justify-center rounded-full align-middle text-canvas-muted transition-[transform,color,background-color] duration-150 ease-out after:absolute after:-inset-2.5 after:content-[''] hover:bg-violet-50 hover:text-canvas-violet focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-violet-400 active:scale-[0.95] ${className}`}
        aria-label={`${label}: sorgu bilgisi`}
        title="Bu rakamın sorgusu ve hesabı"
        onClick={(e) => e.stopPropagation()}
      >
        <Info aria-hidden className="h-3.5 w-3.5" strokeWidth={2.4} />
      </Dialog.Trigger>
      <Panel k={k} refId={ref} label={label} />
    </Dialog.Root>
  );
}

function Panel({ k, refId, label }: { k: Kaynaklar; refId: string | null; label: string }) {
  const canSql = useCan('kart.sql-goster');
  const { formulas, sources } = useMemo(() => collect(k, refId), [k, refId]);
  const dataEnd = sources.find((s) => s.dataEnd)?.dataEnd ?? k.dataEnd ?? null;
  return (
    <Dialog.Portal>
      <Dialog.Backdrop className="fixed inset-0 z-[90] bg-slate-950/40 transition-opacity duration-200 ease-out data-[ending-style]:opacity-0 data-[starting-style]:opacity-0 data-[ending-style]:duration-150" />
      <Dialog.Popup
        className="fixed left-1/2 top-1/2 z-[91] flex max-h-[min(86vh,860px)] w-[min(780px,calc(100vw-32px))] -translate-x-1/2 -translate-y-1/2 flex-col overflow-hidden rounded-3xl bg-white text-canvas-ink shadow-2xl outline-none transition-[transform,opacity] duration-200 ease-[cubic-bezier(0.23,1,0.32,1)] data-[ending-style]:scale-[0.97] data-[starting-style]:scale-[0.97] data-[ending-style]:opacity-0 data-[starting-style]:opacity-0 data-[ending-style]:duration-150 max-sm:inset-x-0 max-sm:bottom-0 max-sm:left-0 max-sm:top-auto max-sm:max-h-[88vh] max-sm:w-full max-sm:translate-x-0 max-sm:translate-y-0 max-sm:rounded-b-none max-sm:duration-[260ms] max-sm:ease-[cubic-bezier(0.32,0.72,0,1)] max-sm:data-[ending-style]:translate-y-full max-sm:data-[starting-style]:translate-y-full max-sm:data-[ending-style]:scale-100 max-sm:data-[starting-style]:scale-100 max-sm:data-[ending-style]:opacity-100 max-sm:data-[starting-style]:opacity-100 max-sm:data-[ending-style]:duration-200 motion-reduce:transition-opacity motion-reduce:data-[ending-style]:scale-100 motion-reduce:data-[starting-style]:scale-100 motion-reduce:max-sm:data-[ending-style]:translate-y-0 motion-reduce:max-sm:data-[starting-style]:translate-y-0 motion-reduce:max-sm:data-[ending-style]:opacity-0 motion-reduce:max-sm:data-[starting-style]:opacity-0"
      >
        <header className="flex items-start justify-between gap-3 border-b border-slate-100 px-5 pb-3 pt-4 max-sm:px-4">
          <div className="min-w-0">
            <div className="text-[10.5px] font-extrabold uppercase tracking-[0.08em] text-canvas-violet">Sorgu bilgisi</div>
            <Dialog.Title className="mt-0.5 text-[17px] font-extrabold leading-snug">{label}</Dialog.Title>
            <Dialog.Description className="mt-1 text-[12px] leading-relaxed text-canvas-muted">
              {dataEnd ? <>Veri {fmtWhen(dataEnd)} tarihine kadar. </> : null}
              {sources.length
                ? `Bu rakam ${sources.length} sorgudan${formulas.length ? ' ve aşağıdaki hesaptan' : ''} gelir.`
                : 'Bu rakam için kayıtlı sorgu yok.'}
            </Dialog.Description>
          </div>
          <Dialog.Close
            className="-mr-1 inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-full text-canvas-muted transition-[transform,background-color] duration-150 ease-out hover:bg-slate-100 active:scale-[0.95]"
            aria-label="Kapat"
          >
            <X aria-hidden className="h-[18px] w-[18px]" />
          </Dialog.Close>
        </header>

        <div className="flex min-h-0 flex-1 flex-col gap-3 overflow-y-auto overscroll-contain px-5 pb-5 pt-3 max-sm:px-4 max-sm:pb-[max(16px,env(safe-area-inset-bottom))]">
          {k.error && <p className="rounded-xl bg-amber-50 px-3 py-2 text-[12.5px] font-semibold text-amber-800">{k.error}</p>}

          {formulas.map((f) => (
            <section key={f.name} className="rounded-2xl bg-violet-50/70 px-3.5 py-2.5">
              <div className="flex items-center gap-1.5 text-[11px] font-extrabold uppercase tracking-wide text-canvas-violet">
                <Sigma aria-hidden className="h-3.5 w-3.5" /> Hesap
              </div>
              <p className="mt-1 text-[12.5px] leading-relaxed text-canvas-ink">{f.text}</p>
            </section>
          ))}

          {sources.length > 1 && canSql && <CopyAll sources={sources} />}
          {!canSql && sources.length > 0 && (
            <p className="rounded-xl bg-slate-50 px-3 py-2 text-[12px] text-canvas-muted">
              SQL metni «SQL'i göster ve kopyala» yetkisiyle görünür; yetki Yönetim ekranında rolünüze eklenir.
            </p>
          )}

          {sources.map((s) => (
            <SourceCard key={s.id} s={s} showSql={canSql} />
          ))}
        </div>
      </Dialog.Popup>
    </Dialog.Portal>
  );
}

function useCopied(): [state: 'idle' | 'done' | 'fail', copy: (text: string) => void] {
  const [state, setState] = useState<'idle' | 'done' | 'fail'>('idle');
  useEffect(() => {
    if (state === 'idle') return;
    const t = window.setTimeout(() => setState('idle'), 1800);
    return () => window.clearTimeout(t);
  }, [state]);
  return [state, (text: string) => void copyText(text).then((ok) => setState(ok ? 'done' : 'fail'))];
}

function CopyButton({ text, label, what }: { text: string; label: string; what: string }) {
  const [state, copy] = useCopied();
  return (
    <button
      type="button"
      onClick={() => copy(text)}
      aria-label={`${what} kopyala`}
      className="inline-flex min-h-9 shrink-0 items-center gap-1.5 rounded-xl bg-slate-900 px-3 text-[12px] font-bold text-white transition-transform duration-150 ease-out active:scale-[0.97]"
    >
      {state === 'done' ? <Check aria-hidden className="h-3.5 w-3.5 text-emerald-300" /> : <Copy aria-hidden className="h-3.5 w-3.5" />}
      <span aria-live="polite">{state === 'done' ? 'Kopyalandı' : state === 'fail' ? 'Seçip kopyalayın' : label}</span>
    </button>
  );
}

function CopyAll({ sources }: { sources: KaynakSorgu[] }) {
  return (
    <div className="flex flex-wrap items-center justify-between gap-2 rounded-2xl border border-slate-100 px-3.5 py-2">
      <span className="text-[12px] font-semibold text-canvas-muted">Sorguların hepsi, her birinin başında adıyla</span>
      <CopyButton text={allSqlText(sources)} label="Hepsini kopyala" what="Bütün sorguları" />
    </div>
  );
}

function SourceCard({ s, showSql }: { s: KaynakSorgu & { isOrigin: boolean }; showSql: boolean }) {
  const stats = s.stats;
  const meta = [
    stats?.rows != null ? `${stats.rows.toLocaleString('tr-TR')} satır` : null,
    fmtMs(stats?.dbMs),
    stats?.ranAt ? `çalıştı ${fmtWhen(stats.ranAt)}` : null,
  ].filter(Boolean);
  return (
    <article className={`rounded-2xl border px-3.5 py-3 ${s.isOrigin ? 'ml-3 border-dashed border-slate-200 max-sm:ml-1.5' : 'border-slate-200'}`}>
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          {s.isOrigin && (
            <div className="mb-0.5 flex items-center gap-1 text-[10.5px] font-extrabold uppercase tracking-wide text-canvas-muted">
              <CornerDownRight aria-hidden className="h-3 w-3" /> Tabloyu dolduran asıl sorgu
            </div>
          )}
          <h3 className="text-[13.5px] font-extrabold leading-snug">{s.title}</h3>
          <div className="mt-1 flex flex-wrap items-center gap-1.5 text-[11px] font-semibold text-canvas-muted">
            <span className="inline-flex items-center gap-1 rounded-md bg-slate-100 px-1.5 py-0.5 text-slate-700">
              <Database aria-hidden className="h-3 w-3" />
              {s.connectionLabel}
              {s.database ? ` · ${s.database}` : ''}
            </span>
            {s.period && <span>{s.period}</span>}
            {meta.map((m) => (
              <span key={m} className="font-mono tabular-nums">{m}</span>
            ))}
          </div>
        </div>
        {showSql && s.sql && <CopyButton text={s.sql} label="Kopyala" what={`${s.title} SQL'ini`} />}
      </div>
      {s.description && <p className="mt-1.5 text-[12px] leading-relaxed text-canvas-muted">{s.description}</p>}
      {showSql && s.sql && (
        <pre
          tabIndex={0}
          aria-label={`${s.title} SQL`}
          className="mt-2 max-h-72 overflow-auto overscroll-contain whitespace-pre rounded-xl bg-slate-950 p-3 font-mono text-[11.5px] leading-relaxed text-slate-100 selection:bg-violet-500/40 max-sm:max-h-60 max-sm:text-[11px]"
        >
          <code>{s.sql}</code>
        </pre>
      )}
    </article>
  );
}


/**
 * Tablo başlığı / kart başlığı için kısayol: metin + yanında «i». Başlık yazısı `label` olarak pencerede görünür.
 *
 *   <th className={th}><InfoLabel k={data.kaynaklar} alan="items[].ciro">Hedef ciro</InfoLabel></th>
 */
export function InfoLabel({
  k,
  alan,
  row,
  label,
  children,
}: {
  k: Kaynaklar | null | undefined;
  alan: string;
  row?: string | number | null;
  label?: string;
  children: string;
}) {
  return (
    <span className="inline-flex items-center gap-1">
      {children}
      <SqlInfo k={k} alan={alan} row={row} label={label ?? children} />
    </span>
  );
}
