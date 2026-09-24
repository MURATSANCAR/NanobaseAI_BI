import { useEffect, useState, type ReactNode } from 'react';
import { useLayout } from './layout';

/**
 * Kartın altındaki "SQL'i göster" şeridi ve açılan panel. Panel kartın genişliğini aşmaz:
 * uzun satırlar kırılır, yükseklik sınırlıdır, fazlası panelin içinde kayar.
 * Kopyalanan metin gösterilenle değil sorgunun kendisiyle aynıdır.
 */

/** Okumak için satır kırma: ana cümlecikler yeni satıra. Yalnız ekranda; kopya özgün metindir. */
const CLAUSE = /\s+(FROM|WHERE|GROUP BY|ORDER BY|HAVING|INNER JOIN|LEFT JOIN|RIGHT JOIN|UNION ALL|UNION)\s+/g;
const pretty = (sql: string) => sql.trim().replace(CLAUSE, '\n$1 ');

/** Pano API'si yalnız güvenli bağlamda (https/localhost) var; müşteri VM'i http üzerinden açılır.
 *  Orada gizli bir metin alanı seçilip eski kopyala komutu kullanılır. */
async function copyText(text: string): Promise<boolean> {
  try {
    if (navigator.clipboard && window.isSecureContext) {
      await navigator.clipboard.writeText(text);
      return true;
    }
  } catch {
    /* aşağıdaki yola düş */
  }
  const ta = document.createElement('textarea');
  ta.value = text;
  ta.setAttribute('readonly', '');
  ta.style.position = 'fixed';
  ta.style.top = '-1000px';
  ta.style.opacity = '0';
  document.body.appendChild(ta);
  ta.select();
  let ok = false;
  try {
    ok = document.execCommand('copy');
  } catch {
    ok = false;
  }
  document.body.removeChild(ta);
  return ok;
}

export default function CardSql({ sql, right, className = '' }: { sql?: string; right?: ReactNode; className?: string }) {
  const [open, setOpen] = useState(false);
  const { bringFront } = useLayout();
  const [copy, setCopy] = useState<'idle' | 'done' | 'fail'>('idle');
  useEffect(() => {
    if (copy === 'idle') return;
    const t = window.setTimeout(() => setCopy('idle'), 2000);
    return () => window.clearTimeout(t);
  }, [copy]);
  // Kart başka bir sorguya geçince (yeni cevap) panel kapanmaz ama kopya işareti sıfırlanır.
  useEffect(() => setCopy('idle'), [sql]);

  if (!sql && !right) return null;
  return (
    <div className={className}>
      <div className="flex flex-wrap items-center justify-between gap-x-2 gap-y-1">
        {sql ? (
          <div className="flex items-center gap-1">
            <button
              type="button"
              onClick={(e) => {
                // Kanvasta panel aşağı uzar ve alttaki kartın üstüne biner; açılan kart öne alınır, yoksa arkada kalır.
                const node = (e.currentTarget.closest('[data-node]') as HTMLElement | null)?.dataset.node;
                if (!open && node) bringFront(node);
                setOpen((v) => !v);
              }}
              aria-expanded={open}
              className="-my-2 flex items-center gap-1 rounded px-1 py-2 text-xs font-bold text-violet transition-transform duration-150 ease-out hover:underline active:scale-[0.97] sm:text-[11px]"
            >
              <svg className="h-3 w-3" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden>
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M16 18l6-6-6-6M8 6l-6 6 6 6" />
              </svg>
              <span>{open ? "SQL'i gizle" : "SQL'i göster"}</span>
            </button>
            <button
              type="button"
              onClick={() => void copyText(sql).then((ok) => setCopy(ok ? 'done' : 'fail'))}
              title="SQL'i kopyala"
              className="-my-2 flex items-center gap-1 rounded px-1 py-2 text-xs font-bold text-muted transition-transform duration-150 ease-out hover:text-ink active:scale-[0.97] sm:text-[11px]"
            >
              {copy === 'done' ? (
                <svg className="h-3 w-3 text-mintSuccess" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden>
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M5 13l4 4L19 7" />
                </svg>
              ) : (
                <svg className="h-3 w-3" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden>
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M8 7V5a2 2 0 012-2h8a2 2 0 012 2v10a2 2 0 01-2 2h-2M8 7H6a2 2 0 00-2 2v10a2 2 0 002 2h8a2 2 0 002-2v-2M8 7h6a2 2 0 012 2v6" />
                </svg>
              )}
              <span aria-live="polite">{copy === 'done' ? 'Kopyalandı' : copy === 'fail' ? 'Seçip kopyalayın' : 'Kopyala'}</span>
            </button>
          </div>
        ) : (
          <span />
        )}
        {right}
      </div>
      {sql && open && (
        <pre
          data-nodrag
          className="mt-2 max-h-56 w-full min-w-0 cursor-text select-text overflow-y-auto overscroll-contain whitespace-pre-wrap rounded-lg bg-slate-950 p-2.5 font-mono text-[11px] font-normal leading-relaxed text-slate-100 [overflow-wrap:anywhere] selection:bg-violet/40"
        >
          {pretty(sql)}
        </pre>
      )}
    </div>
  );
}
