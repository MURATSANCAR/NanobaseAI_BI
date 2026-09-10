/**
 * Sohbette çıkan bir cevabın masaya iliştirilmiş hâli.
 *
 * Cevap zaten hem SQL'i hem nasıl çizileceğini taşıyor; iliştirmek bunları saklayıp sorguyu masada
 * tekrar çalıştırmaktan ibaret. Rakam donmuş bir ekran görüntüsü değil, her açılışta yeniden
 * hesaplanan canlı bir sorgu.
 *
 * Bir uyarı görünür yerde duruyor: soru bir dönem söylüyorsa (ör. "2026 toptan ciro") o dönem
 * SQL'in içindedir ve masanın üstündeki yıl seçicisi bu kartı değiştirmez. Kartın kendi sorusunu
 * göstermek, sessizce yanlış yıl göstermekten iyidir.
 */
import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { AlertTriangle, ChartNoAxesColumn, Loader2 } from 'lucide-react';
import clsx from 'clsx';
import { runSql, type WidgetSpec } from '../lib/engine';
import { ResultChart, CHART_LABEL, chartOptions, type ChartKind } from './ResultChart';
import type { Tile } from '../lib/board';

export function PinnedCard({
  tile, onChart,
}: {
  tile: Extract<Tile, { kind: 'pinned' }>;
  onChart: (id: string, chart: ChartKind) => void;
}) {
  const [open, setOpen] = useState(false);
  const q = useQuery({
    queryKey: ['pinned', tile.id],
    queryFn: () => runSql(tile.sql, 500, tile.question),
    staleTime: 5 * 60_000,
    refetchInterval: 5 * 60_000,
    refetchIntervalInBackground: false,
    retry: 1,
  });

  const widget: WidgetSpec = {
    id: tile.id, type: tile.chart, title: tile.title,
    x_key: tile.xKey, y_key: tile.yKey, label_key: tile.labelKey, value_key: tile.valueKey,
    format: tile.format as WidgetSpec['format'],
  };
  const rows = q.data?.records ?? [];
  const options = rows.length ? chartOptions(rows, widget) : [];

  return (
    <section className="card flex h-full flex-col p-4 sm:p-5">
      <header className="flex items-start gap-2">
        <div className="min-w-0 flex-1">
          <h3 className="truncate font-display text-[15px] font-semibold leading-tight">{tile.title}</h3>
          <p className="mt-0.5 truncate text-[11px] text-ink-muted" title={tile.question}>
            sohbetten · «{tile.question}»
          </p>
        </div>
        {options.length > 1 && (
          <div className="relative shrink-0">
            <button type="button" onClick={() => setOpen((v) => !v)}
              aria-label="Grafik tipini değiştir"
              className="inline-flex items-center gap-1 rounded-lg border border-line bg-white px-1.5 py-1 text-[10px] text-ink-muted hover:border-brand/40">
              <ChartNoAxesColumn size={12} /> {CHART_LABEL[tile.chart as ChartKind] ?? tile.chart}
            </button>
            {open && (
              <ul className="absolute right-0 z-20 mt-1 w-36 overflow-hidden rounded-xl border border-line bg-white py-1 shadow-card">
                {options.map((k) => (
                  <li key={k}>
                    <button type="button"
                      onClick={() => { onChart(tile.id, k); setOpen(false); }}
                      className={clsx('block w-full px-2.5 py-1 text-left text-[11px] hover:bg-brand-soft',
                        tile.chart === k ? 'font-semibold text-brand-deep' : 'text-ink-muted')}>
                      {CHART_LABEL[k]}
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}
      </header>

      <div className="mt-1 min-h-0 flex-1">
        {q.isPending && (
          <div className="flex h-32 items-center justify-center text-[12px] text-ink-muted">
            <Loader2 size={14} className="mr-2 animate-spin" /> hesaplanıyor…
          </div>
        )}
        {q.isError && (
          <div className="flex items-start gap-2 rounded-lg border border-warn/40 bg-warn/5 p-2.5 text-[11.5px]">
            <AlertTriangle size={14} className="mt-0.5 shrink-0 text-warn" />
            <span>Sorgu çalışmadı. <span className="text-ink-muted">{(q.error as Error).message}</span></span>
          </div>
        )}
        {q.data && rows.length === 0 && (
          <div className="py-6 text-center text-[12px] text-ink-muted">Bu sorgu şu an satır döndürmüyor.</div>
        )}
        {q.data && rows.length > 0 && (
          <ResultChart widget={widget} records={rows} wide chart={tile.chart as ChartKind}
                       height={tile.span === 1 ? 150 : 210} />
        )}
      </div>

      {q.data?.computedAt != null && (
        <div className="mt-1.5 text-right text-[10px] text-ink-faint">
          {rows.length.toLocaleString('tr-TR')} satır · canlı sorgu
        </div>
      )}
    </section>
  );
}
