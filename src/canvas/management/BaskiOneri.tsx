import { forwardRef, useCallback, useEffect, useMemo, useState, type HTMLAttributes } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { TableVirtuoso, type TableComponents } from 'react-virtuoso';
import { ArrowDown, ArrowDownToLine, ArrowUp, Code2, Info, Loader2, RefreshCw, Search, X } from 'lucide-react';
import Shell from '../stitch/Shell';
import { managementRail } from '../stitch/screens';
import { ENGINE_ENABLED } from '../engine';
import { clockOffset, formatCell, managementApi, mergeSnapshot, numberOf, ONERI_TONE, type ReportColumn, type ReportSnapshot, type ReportView } from './api';
import LiveStatus from './LiveStatus';
import SourcesSheet, { focusOf, type SheetFocus } from './SourcesSheet';
import SearchSelect from '../components/SearchSelect';
import './management.css';

const REPORT_ID = 'baski-oneri';
const ROUTE = '/yonetim-raporlari/baski-oneri';

type Row = ReportView['rows'][number];
type Sort = { index: number; dir: 1 | -1 } | null;

const FILTER_LABELS: Record<string, string> = {
  baski_durum: 'Baskı durumu',
  yayinevi: 'Yayınevi',
  yazar: 'Yazar',
  statu: 'Statü',
  urun_adi: 'Ürün Adı',
};

const TEXTUAL = new Set(['text', 'oneri', 'date']);
const isNum = (c: ReportColumn) => !TEXTUAL.has(c.format);

/** Power BI toplam satırı: toplanan kolonlar Σ, Tükenme Süresi ölçüsü Σ StokAdedi ÷ Σ OrtSatisHizi, gerisi boş. */
function totalsOf(view: ReportView, rows: Row[]): Array<number | null> {
  const idx = new Map(view.columns.map((c, i) => [c.key, i]));
  const sumAt = (i: number | undefined) => {
    if (i === undefined) return null;
    let any = false;
    let acc = 0;
    for (const r of rows) {
      const n = numberOf(r[i]);
      if (n === null) continue; // BLANK + x = x
      any = true;
      acc += n;
    }
    return any ? acc : null;
  };
  return view.columns.map((c, i) => {
    if (c.total === 'sum') return sumAt(i);
    if (c.total === 'tukenme') {
      const stok = sumAt(idx.get('stok_adedi'));
      const hiz = sumAt(idx.get('ort_satis_hizi'));
      if (stok === null && hiz === null) return null;
      return (stok ?? 0) / (hiz ?? 0); // JS bölmesi DAX gibi: 5/0 = ∞, 0/0 = NaN
    }
    return null;
  });
}

const norm = (s: string) => s.toLocaleLowerCase('tr');

/** Kolon genişlikleri: yapışkan ilk iki kolonun sol ofseti bunlara dayanır. */
const widthOf = (c: ReportColumn) =>
  c.key === 'stok_kodu' ? 132 : c.key === 'urun_adi' ? 240 : c.format === 'text' ? 170 : c.format === 'oneri' ? 124 : c.format === 'date' ? 112 : 104;

function csvOf(view: ReportView, rows: Row[]) {
  const esc = (v: unknown) => {
    const s = v === null || v === undefined ? '' : String(v);
    return /[;"\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
  };
  const num = (v: unknown) => (typeof v === 'number' ? String(v).replace('.', ',') : esc(v));
  const lines = [view.columns.map((c) => esc(c.label)).join(';')];
  for (const r of rows) lines.push(view.columns.map((c, i) => (c.format === 'text' || c.format === 'oneri' || c.format === 'date' ? esc(r[i]) : num(r[i]))).join(';'));
  // Excel Türkçe yerelinde noktalı virgül ve BOM ile doğru açılır.
  return '﻿' + lines.join('\r\n');
}

export default function BaskiOneri() {
  const queryClient = useQueryClient();
  const key = ['management-report', REPORT_ID];
  // Sunucu Logo ve CRM'i beş dakikada bir okur. Ekran yalnız durumu sorar (`since`); veri değiştiyse
  // yenisi gelir, değişmediyse ekrandaki veri olduğu gibi kalır.
  const report = useQuery({
    queryKey: key,
    queryFn: async () => {
      const prev = queryClient.getQueryData<ReportSnapshot>(key);
      return mergeSnapshot(prev, await managementApi.report(REPORT_ID, prev?.data ? prev.updatedAt : undefined));
    },
    enabled: ENGINE_ENABLED,
    retry: false,
    refetchOnWindowFocus: true,
    refetchIntervalInBackground: false,
    refetchInterval: (q) => (q.state.data?.refreshing || !q.state.data?.data ? 3000 : 15_000),
  });
  const refresh = useMutation({
    mutationFn: () => managementApi.refresh(REPORT_ID),
    onSuccess: (snap) => queryClient.setQueryData<ReportSnapshot>(key, (prev) => mergeSnapshot(prev, snap)),
  });
  const offset = clockOffset(report.data, report.dataUpdatedAt);

  const snap = report.data;
  const views = snap?.data?.views ?? [];
  const [viewId, setViewId] = useState('tekrar');
  const view = views.find((v) => v.id === viewId) ?? views[0];

  const [search, setSearch] = useState('');
  const [oneri, setOneri] = useState<Set<string>>(new Set());
  const [selects, setSelects] = useState<Record<string, string>>({});
  const [sort, setSort] = useState<Sort>(null);
  // Açılış süzgeçleri seçili başlar; burada yalnız kullanıcının kaldırdıkları tutulur.
  const [dropped, setDropped] = useState<Set<string>>(new Set());
  const [sheet, setSheet] = useState<{ open: boolean; focus: SheetFocus }>({ open: false, focus: { kind: 'all' } });

  // Görünüm değişince süzgeçler o görünüme aittir; taşınmaz.
  useEffect(() => {
    setOneri(new Set());
    setSelects({});
    setDropped(new Set());
    setSort(null);
  }, [viewId]);

  const presets = view?.defaultFilters ?? [];

  const colIndex = useMemo(() => new Map((view?.columns ?? []).map((c, i) => [c.key, i])), [view]);
  const oneriIdx = colIndex.get('oneri');

  const options = useMemo(() => {
    const out: Record<string, string[]> = {};
    if (!view) return out;
    for (const key of view.filters) {
      if (key === 'oneri') continue;
      const i = colIndex.get(key);
      if (i === undefined) continue;
      out[key] = [...new Set(view.rows.map((r) => r[i]).filter((v): v is string => typeof v === 'string' && v !== ''))].sort((a, b) =>
        a.localeCompare(b, 'tr'),
      );
    }
    return out;
  }, [view, colIndex]);

  // Öneri sayaçları diğer süzgeçlere göre sayılır: çip kendi seçiminden etkilenmez.
  const { rows, counts } = useMemo(() => {
    if (!view) return { rows: [] as Row[], counts: {} as Record<string, number> };
    const needle = norm(search.trim());
    const textIdx = ['stok_kodu', 'urun_adi', 'yazar', 'yayinevi'].map((k) => colIndex.get(k)).filter((i): i is number => i !== undefined);
    const pre = view.rows.filter((r) => {
      for (const preset of view.defaultFilters ?? []) {
        if (dropped.has(preset.key)) continue;
        const i = colIndex.get(preset.key);
        if (i === undefined) continue;
        // Power BI'da boş değer de seçiliydi; null ile boş metin aynı sayılır.
        if (!preset.values.some((v) => (v ?? '') === (r[i] ?? ''))) return false;
      }
      for (const [key, value] of Object.entries(selects)) {
        if (value && r[colIndex.get(key)!] !== value) return false;
      }
      if (needle && !textIdx.some((i) => norm(String(r[i] ?? '')).includes(needle))) return false;
      return true;
    });
    const counts: Record<string, number> = {};
    if (oneriIdx !== undefined) for (const r of pre) counts[String(r[oneriIdx])] = (counts[String(r[oneriIdx])] ?? 0) + 1;
    let out = oneri.size && oneriIdx !== undefined ? pre.filter((r) => oneri.has(String(r[oneriIdx]))) : pre;
    if (sort) {
      const { index, dir } = sort;
      // Power BI sırası: boş en küçük değerdir (artanda başta), NaN her iki yönde en sonda.
      const numeric = isNum(view.columns[index]);
      const blank = (v: unknown) => v === null || v === undefined || v === '';
      out = [...out].sort((a, b) => {
        const x = a[index];
        const y = b[index];
        if (blank(x) || blank(y)) return blank(x) && blank(y) ? 0 : (blank(x) ? -1 : 1) * dir;
        if (numeric) {
          const nx = numberOf(x) ?? 0;
          const ny = numberOf(y) ?? 0;
          if (Number.isNaN(nx) || Number.isNaN(ny)) return Number.isNaN(nx) && Number.isNaN(ny) ? 0 : Number.isNaN(nx) ? 1 : -1;
          return (nx === ny ? 0 : nx < ny ? -1 : 1) * dir;
        }
        return String(x).localeCompare(String(y), 'tr') * dir;
      });
    }
    return { rows: out, counts };
  }, [view, search, selects, oneri, dropped, sort, colIndex, oneriIdx]);

  const toggleSort = (index: number) =>
    setSort((s) => (s?.index !== index ? { index, dir: -1 } : s.dir === -1 ? { index, dir: 1 } : null));

  const openSheet = useCallback((focus: SheetFocus) => setSheet({ open: true, focus }), []);

  const download = () => {
    if (!view) return;
    const blob = new Blob([csvOf(view, rows)], { type: 'text/csv;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `baski-oneri-${view.id}-${snap?.data?.asOf ?? 'rapor'}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const refreshing = refresh.isPending || !!snap?.refreshing;
  const levels = snap?.data?.oneriLevels ?? [];
  const activeFilters =
    oneri.size + Object.values(selects).filter(Boolean).length + (search ? 1 : 0) + (presets.length - dropped.size);

  const head = {
    tenant: 'Timaş Yayınları',
    section: 'Yönetim Raporları',
    crumb: 'Yeni Baskı Öneri',
    source: 'Logo + CRM',
    presence: snap?.updatedAt ? `Veri: ${new Date(snap.updatedAt * 1000).toLocaleTimeString('tr-TR', { hour: '2-digit', minute: '2-digit' })}` : 'Hazırlanıyor',
  };

  return (
    <Shell head={head} rail={managementRail(ROUTE)}>
      <main className="mg-main">
        <div className="mg-page">
          <header className="mg-heading">
            <div>
              <div className="mg-eyebrow">YÖNETİM RAPORLARI / BASKI</div>
              <h1>
                Hangi kitap yeniden basılmalı<span>?</span>
              </h1>
              <p>Satış hızına göre stok kaç ay yeter; bekleyen sipariş ve CRM önerisiyle birlikte.</p>
            </div>
            <div className="mg-actions">
              <button type="button" className="mg-button" onClick={() => openSheet({ kind: 'all' })}>
                <Code2 size={16} /> SQL ve hesaplar
              </button>
              <button type="button" className="mg-button" onClick={download} disabled={!view || rows.length === 0}>
                <ArrowDownToLine size={16} /> CSV
              </button>
              <button type="button" className="mg-button" onClick={() => refresh.mutate()} disabled={refreshing || !ENGINE_ENABLED}>
                <RefreshCw size={16} className={refreshing ? 'animate-spin' : ''} />
                {refreshing ? 'Yenileniyor' : 'Verileri yenile'}
              </button>
            </div>
          </header>

          {snap && <LiveStatus snap={snap} offset={offset} />}
          {snap?.error && (snap.failedAt ?? 0) >= (snap.updatedAt ?? 0) && (
            <p className="mg-banner" role="status">{snap.error}{snap.data ? ' Ekrandaki veri son başarılı okumadır.' : ''}</p>
          )}
          {refresh.error && <p className="mg-banner" role="status">{(refresh.error as Error).message}</p>}
          {snap?.data?.warnings?.map((w) => (
            <p key={w} className="mg-banner" role="status">{w}</p>
          ))}

          {!view ? (
            <section className="mg-empty" aria-busy={report.isFetching || refreshing}>
              {report.error ? (
                <>
                  <h2>Rapor açılamadı</h2>
                  <p>{(report.error as Error).message}</p>
                  <button type="button" className="mg-button" onClick={() => report.refetch()}>Tekrar dene</button>
                </>
              ) : snap?.error ? (
                <>
                  <h2>Rapor hazırlanamadı</h2>
                  <p>Veri kaynaklarından biri yanıt vermedi. Ayrıntı yukarıda; “Verileri yenile” ile tekrar denenebilir.</p>
                </>
              ) : (
                <>
                  <Loader2 className="animate-spin" size={22} />
                  <h2>Rapor hazırlanıyor</h2>
                  <p>Logo ve CRM’den dokuz sorgu okunuyor. İlk okuma birkaç dakika sürebilir; sonra veriler beş dakikada bir kendiliğinden yenilenir.</p>
                </>
              )}
            </section>
          ) : (
            <>
              <div className="mg-toolbar">
                <div className="mg-seg" role="tablist" aria-label="Rapor görünümü">
                  {views.map((v) => (
                    <button key={v.id} type="button" role="tab" aria-selected={v.id === view.id} className="mg-seg-item" onClick={() => setViewId(v.id)}>
                      {v.title}
                      <span className="mg-seg-count">{v.rows.length.toLocaleString('tr-TR')}</span>
                    </button>
                  ))}
                </div>
                <label className="mg-search">
                  <Search size={15} aria-hidden />
                  <input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Kitap, yazar, stok kodu" aria-label="Rapor içinde ara" />
                  {search && (
                    <button type="button" onClick={() => setSearch('')} aria-label="Aramayı temizle">
                      <X size={14} />
                    </button>
                  )}
                </label>
              </div>

              <div className="mg-levels" role="group" aria-label="Öneriye göre süz">
                {levels.map((level) => {
                  const on = oneri.has(level);
                  return (
                    <button
                      key={level}
                      type="button"
                      aria-pressed={on}
                      className={`mg-level ${ONERI_TONE[level] ?? ''}${on ? ' is-on' : ''}`}
                      onClick={() =>
                        setOneri((s) => {
                          const next = new Set(s);
                          if (next.has(level)) next.delete(level);
                          else next.add(level);
                          return next;
                        })
                      }
                    >
                      <span className="mg-level-dot" aria-hidden />
                      <span className="mg-level-name">{level}</span>
                      <strong>{(counts[level] ?? 0).toLocaleString('tr-TR')}</strong>
                    </button>
                  );
                })}
              </div>

              {presets.length > 0 && (
                <div className="mg-presets" role="group" aria-label="Power BI açılış süzgeçleri">
                  <span className="mg-presets-label">Power BI açılışı</span>
                  {presets.map((preset) => {
                    const on = !dropped.has(preset.key);
                    const values = preset.values.map((v) => v ?? '(boş)');
                    return (
                      <button
                        key={preset.key}
                        type="button"
                        aria-pressed={on}
                        title={`${FILTER_LABELS[preset.key] ?? preset.key}: ${values.join(' · ')}`}
                        className={`mg-preset${on ? ' is-on' : ''}`}
                        onClick={() =>
                          setDropped((s) => {
                            const next = new Set(s);
                            if (next.has(preset.key)) next.delete(preset.key);
                            else next.add(preset.key);
                            return next;
                          })
                        }
                      >
                        {FILTER_LABELS[preset.key] ?? preset.key}
                        <span>{values.length}</span>
                        {on && <X size={12} aria-hidden />}
                      </button>
                    );
                  })}
                </div>
              )}

              <div className="mg-filters">
                {Object.entries(options).map(([key, values]) => (
                  <div key={key} className="mg-select">
                    <span aria-hidden>{FILTER_LABELS[key] ?? key}</span>
                    <SearchSelect
                      label={FILTER_LABELS[key] ?? key}
                      options={values}
                      value={selects[key] ?? ''}
                      onChange={(v) => setSelects((s) => ({ ...s, [key]: v }))}
                    />
                  </div>
                ))}
                <p className="mg-count" aria-live="polite">
                  <strong>{rows.length.toLocaleString('tr-TR')}</strong> kitap · {view.hint.toLocaleLowerCase('tr')}
                  {activeFilters > 0 && (
                    <button
                      type="button"
                      className="mg-link"
                      onClick={() => {
                        setOneri(new Set());
                        setSelects({});
                        setSearch('');
                        setDropped(new Set(presets.map((p) => p.key)));
                      }}
                    >
                      Süzgeçleri temizle
                    </button>
                  )}
                </p>
              </div>

              <ReportTable view={view} rows={rows} sort={sort} onSort={toggleSort} onSource={openSheet} />
            </>
          )}
        </div>
      </main>
      <SourcesSheet
        reportId={REPORT_ID}
        open={sheet.open}
        focus={sheet.focus}
        columns={view?.columns ?? []}
        onOpenChange={(open) => setSheet((s) => ({ ...s, open }))}
      />
    </Shell>
  );
}

/** Virtuoso tabloyu kendisi kurar; bileşenler sınıf ve sabit düzen için sarılır. */
const tableComponents: TableComponents<Row> = {
  Table: (props) => <table {...props} className="mg-table" />,
  TableHead: forwardRef<HTMLTableSectionElement, HTMLAttributes<HTMLTableSectionElement>>((props, ref) => <thead {...props} ref={ref} className="mg-thead" />),
  TableRow: (props) => <tr {...props} />,
};

function ReportTable({
  view,
  rows,
  sort,
  onSort,
  onSource,
}: {
  view: ReportView;
  rows: Row[];
  sort: Sort;
  onSort: (index: number) => void;
  onSource: (f: SheetFocus) => void;
}) {
  const cols = view.columns;
  // Şablondaki gibi toplam satırı; Power BI görselinde kolon grup başlığı yoktur.
  const totals = useMemo(() => totalsOf(view, rows), [view, rows]);
  const hasTotals = cols.some((c) => c.total);
  const stickyLeft = (i: number) => (i === 0 ? 0 : i === 1 ? widthOf(cols[0]) : undefined);

  if (rows.length === 0) {
    return <div className="mg-table-wrap mg-table-empty">Bu süzgeçlere uyan kitap yok.</div>;
  }

  return (
    <div className="mg-table-wrap">
      <TableVirtuoso
        data={rows}
        components={tableComponents}
        increaseViewportBy={400}
        fixedHeaderContent={() => (
          <>
            <tr>
              {cols.map((c, i) => {
                const left = stickyLeft(i);
                const active = sort?.index === i;
                return (
                  <th
                    key={c.key}
                    scope="col"
                    style={{ width: widthOf(c), minWidth: widthOf(c), left }}
                    className={(left !== undefined ? `mg-sticky mg-sticky-${i}` : '') + (c.format !== 'text' && c.format !== 'oneri' && c.format !== 'date' ? ' is-num' : '')}
                    aria-sort={active ? (sort!.dir === 1 ? 'ascending' : 'descending') : undefined}
                  >
                    <div className="mg-th">
                      <button type="button" className="mg-th-sort" onClick={() => onSort(i)} title="Sırala">
                        {c.label}
                        {active && (sort!.dir === 1 ? <ArrowUp size={12} /> : <ArrowDown size={12} />)}
                      </button>
                      <button type="button" className="mg-th-src" onClick={() => onSource(focusOf(c))} aria-label={`${c.label}: kaynağını göster`} title="Kaynağı ve SQL">
                        <Info size={12} />
                      </button>
                    </div>
                  </th>
                );
              })}
            </tr>
          </>
        )}
        fixedFooterContent={
          hasTotals
            ? () => (
                <tr className="mg-total-row">
                  {cols.map((c, i) => {
                    const left = stickyLeft(i);
                    const v = totals[i];
                    return (
                      <td key={c.key} style={{ left }} className={(left !== undefined ? `mg-sticky mg-sticky-${i}` : '') + (isNum(c) ? ' is-num' : '')}>
                        {i === 0 ? 'Toplam' : v === null ? '' : formatCell(v, c.format)}
                      </td>
                    );
                  })}
                </tr>
              )
            : undefined
        }
        itemContent={(_, row) =>
          cols.map((c, i) => {
            const left = stickyLeft(i);
            const value = row[i];
            const cls = (left !== undefined ? `mg-sticky mg-sticky-${i}` : '') + (c.format !== 'text' && c.format !== 'oneri' && c.format !== 'date' ? ' is-num' : '');
            return (
              <td key={c.key} style={{ left }} className={cls || undefined}>
                {c.format === 'oneri' && value ? (
                  <span className={`mg-badge ${ONERI_TONE[String(value)] ?? ''}`}>{String(value)}</span>
                ) : (
                  formatCell(value, c.format)
                )}
              </td>
            );
          })
        }
      />
    </div>
  );
}
