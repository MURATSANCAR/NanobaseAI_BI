import { useState } from 'react';
import { Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { ArrowRight, BookOpen } from 'lucide-react';
import { ENGINE_ENABLED } from '../engine';
import { productionApi } from '../editorial/production/api';
import { FOLDED_ROWS, dayLabel, printLabel, shouldShow, visibleRows } from './newPrints';

/**
 * Kampüs «Matbaadan yeni çıkanlar»: M12 üretim kartlarından son N günde (Yönetim ayarı PRODUCTION_NEW_PRINTS_DAYS,
 * varsayılan 30) baskısı gerçekleşen kitaplar. Kaynak hazır değilse, okunamazsa ya da pencerede baskı yoksa bölüm
 * hiç görünmez (örnek içerik gösterilmez). Adet ve maliyet gelmez; üretim sayfası yetkisi olana ekrana bağlantı.
 */
export default function NewPrintsCard({ canOpenProduction }: { canOpenProduction: boolean }) {
  const [expanded, setExpanded] = useState(false);
  const q = useQuery({
    queryKey: ['production', 'new-prints'],
    queryFn: productionApi.newPrints,
    enabled: ENGINE_ENABLED,
    retry: false,
    staleTime: 5 * 60_000,
    // İlk açılışta kaynak henüz okunmadıysa (ready: false) kısa süre sonra yeniden sorulur; sonra 15 dk'da bir.
    refetchInterval: (query) => (query.state.data && !query.state.data.ready ? 60_000 : 15 * 60_000),
  });
  const data = q.data;
  if (!shouldShow(data, q.isError)) return null;
  const rows = visibleRows(data.items, expanded);
  const hidden = data.items.length - FOLDED_ROWS;

  return (
    <section id="yeni-kitaplar" className="kp-card rounded-3xl border border-white/80 bg-white/90 p-4">
      <div className="mb-3 flex items-center justify-between gap-2">
        <div className="flex min-w-0 items-center gap-2">
          <BookOpen aria-hidden className="h-4 w-4 shrink-0 text-violet" />
          <h3 className="kp-display truncate text-xs font-bold uppercase tracking-wider text-ink">Matbaadan Yeni Çıkanlar</h3>
        </div>
        <span className="kp-mono shrink-0 text-[11px] font-semibold text-muted">
          {data.items.length} baskı · {data.days} gün
        </span>
      </div>
      <ul className="flex flex-col divide-y divide-slate-100">
        {rows.map((b) => (
          <li key={b.cardId} className="flex min-h-11 items-center justify-between gap-3 py-2">
            <div className="min-w-0">
              <p className="truncate text-xs font-bold text-ink" title={b.title ?? undefined}>
                {b.title ?? 'Adsız kitap'}
              </p>
              <p className="text-[11px] text-muted">
                <span className={b.firstPrint ? 'font-semibold text-violet' : 'font-semibold text-emerald-700'}>{printLabel(b)}</span>
              </p>
            </div>
            <span className="kp-mono shrink-0 text-[11px] text-muted">{dayLabel(b.day)}</span>
          </li>
        ))}
      </ul>
      <div className="mt-2 flex flex-wrap items-center justify-between gap-2">
        {hidden > 0 ? (
          <button
            type="button"
            aria-expanded={expanded}
            onClick={() => setExpanded((v) => !v)}
            className="kp-press min-h-11 rounded-lg px-2 text-[11px] font-semibold text-violet hover:bg-violet/5 sm:min-h-0 sm:py-1"
          >
            {expanded ? 'Daha az göster' : `Tümünü göster (+${hidden})`}
          </button>
        ) : (
          <span className="text-[11px] text-muted">Baskı günü üretim kaydından.</span>
        )}
        {canOpenProduction && (
          <Link
            to="/uretim"
            className="kp-press flex min-h-11 items-center gap-1 rounded-lg px-2 text-[11px] font-semibold text-violet hover:bg-violet/5 sm:min-h-0 sm:py-1"
          >
            Üretim takvimi <ArrowRight aria-hidden className="h-3.5 w-3.5" />
          </Link>
        )}
      </div>
    </section>
  );
}
