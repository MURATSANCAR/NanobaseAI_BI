import { lazy, Suspense, useEffect, useMemo, useState } from 'react';
import { Dialog } from '@base-ui/react/dialog';
import { useQuery } from '@tanstack/react-query';
import { Database, Sigma, X } from 'lucide-react';
import { managementApi, type ReportColumn, type ReportSource } from './api';

const SqlCode = lazy(() => import('./SqlCode'));

/** Neyin gösterileceği: bir sorgu, bir hesap ya da genel görünüm. */
export type SheetFocus = { kind: 'all' } | { kind: 'source'; id: string } | { kind: 'formula'; name: string };

export function focusOf(column: ReportColumn): SheetFocus {
  return column.source.startsWith('hesap:')
    ? { kind: 'formula', name: column.source.slice(6) }
    : { kind: 'source', id: column.source };
}

type Tab = 'sources' | 'formulas' | 'notes';

export default function SourcesSheet({
  reportId,
  open,
  focus,
  columns,
  onOpenChange,
}: {
  reportId: string;
  open: boolean;
  focus: SheetFocus;
  columns: ReportColumn[];
  onOpenChange: (open: boolean) => void;
}) {
  const query = useQuery({
    queryKey: ['management-sources', reportId],
    queryFn: () => managementApi.sources(reportId),
    enabled: open,
    staleTime: 5 * 60_000,
    retry: false,
  });
  const [tab, setTab] = useState<Tab>('sources');
  const [expanded, setExpanded] = useState<string | null>(null);

  // Açılırken odak: kolondan gelindiyse o sorgu açık ve görünür, hesaptan gelindiyse formül sekmesi.
  useEffect(() => {
    if (!open) return;
    if (focus.kind === 'formula') setTab('formulas');
    else setTab('sources');
    setExpanded(focus.kind === 'source' ? focus.id : null);
  }, [open, focus]);

  useEffect(() => {
    if (!open || !query.data) return;
    const id = focus.kind === 'source' ? `mg-src-${focus.id}` : focus.kind === 'formula' ? `mg-f-${focus.name}` : null;
    if (id) requestAnimationFrame(() => document.getElementById(id)?.scrollIntoView({ block: 'start' }));
  }, [open, focus, query.data, tab]);

  // Hangi kolon hangi sorgudan besleniyor: kaynak kartında listelenir.
  const feeds = useMemo(() => {
    const map = new Map<string, string[]>();
    for (const c of columns) {
      const list = map.get(c.source) ?? [];
      if (!list.includes(c.label)) list.push(c.label);
      map.set(c.source, list);
    }
    return map;
  }, [columns]);

  const groups = useMemo(() => {
    const src = query.data?.sources ?? [];
    return (['logo', 'crm'] as const)
      .map((conn) => ({ conn, items: src.filter((s) => s.connection === conn) }))
      .filter((g) => g.items.length);
  }, [query.data]);

  const focusedFormula = focus.kind === 'formula' ? focus.name : null;

  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Backdrop className="mg-scrim" />
        <Dialog.Popup className="mg-sheet" aria-describedby={undefined}>
          <header className="mg-sheet-head">
            <div>
              <div className="mg-eyebrow">VERİ KAYNAĞI</div>
              <Dialog.Title className="mg-sheet-title">Bu rapor nereden geliyor?</Dialog.Title>
              <Dialog.Description className="mg-sheet-sub">
                Ekrandaki her sayı aşağıdaki sorgulardan okunur ve buradaki hesaplarla birleştirilir. Gösterilen SQL, sunucuda çalışan dosyanın kendisidir.
              </Dialog.Description>
            </div>
            <Dialog.Close className="mg-icon-button" aria-label="Kapat">
              <X size={18} />
            </Dialog.Close>
          </header>

          <div className="mg-seg" role="tablist" aria-label="Kaynak bölümleri">
            {(
              [
                ['sources', `Sorgular${query.data ? ` (${query.data.sources.length})` : ''}`],
                ['formulas', 'Hesaplamalar'],
                ['notes', 'Power BI’dan farklar'],
              ] as Array<[Tab, string]>
            ).map(([id, label]) => (
              <button key={id} type="button" role="tab" aria-selected={tab === id} className="mg-seg-item" onClick={() => setTab(id)}>
                {label}
              </button>
            ))}
          </div>

          <div className="mg-sheet-body">
            {query.isLoading && <p className="mg-muted">Sorgular getiriliyor…</p>}
            {query.error && <p className="mg-error">{(query.error as Error).message}</p>}

            {query.data && tab === 'sources' &&
              groups.map((g) => (
                <section key={g.conn} className="mg-src-group">
                  <h3>
                    <Database size={14} /> {g.items[0].database}
                  </h3>
                  {g.items.map((s) => (
                    <SourceCard
                      key={s.id}
                      source={s}
                      feeds={feeds.get(s.id) ?? []}
                      open={expanded === s.id}
                      highlighted={focus.kind === 'source' && focus.id === s.id}
                      onToggle={() => setExpanded((e) => (e === s.id ? null : s.id))}
                    />
                  ))}
                </section>
              ))}

            {query.data && tab === 'formulas' && (
              <ul className="mg-formulas">
                {query.data.formulas.map((f) => (
                  <li key={f.name} id={`mg-f-${f.name}`} className={focusedFormula === f.name ? 'is-focused' : undefined}>
                    <strong>
                      <Sigma size={14} /> {f.name}
                    </strong>
                    <p>{f.text}</p>
                  </li>
                ))}
              </ul>
            )}

            {query.data && tab === 'notes' && (
              <ul className="mg-notes">
                {query.data.notes.map((n) => (
                  <li key={n}>{n}</li>
                ))}
              </ul>
            )}
          </div>
        </Dialog.Popup>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

function SourceCard({
  source,
  feeds,
  open,
  highlighted,
  onToggle,
}: {
  source: ReportSource;
  feeds: string[];
  open: boolean;
  highlighted: boolean;
  onToggle: () => void;
}) {
  const stats = source.stats;
  return (
    <article id={`mg-src-${source.id}`} className={'mg-src' + (highlighted ? ' is-focused' : '')}>
      <button type="button" className="mg-src-head" aria-expanded={open} onClick={onToggle}>
        <span className="mg-src-name">
          <strong>{source.title}</strong>
          <span>{source.description}</span>
        </span>
        <span className="mg-src-stats">
          {stats?.skipped ? stats.skipped : stats ? `${stats.rows.toLocaleString('tr-TR')} satır` : 'henüz çalışmadı'}
          {stats?.dbMs != null && !stats.skipped && <em>{(stats.dbMs / 1000).toLocaleString('tr-TR', { maximumFractionDigits: 1 })} sn</em>}
        </span>
      </button>
      {feeds.length > 0 && (
        <div className="mg-feeds" aria-label="Beslediği kolonlar">
          {feeds.map((f) => (
            <span key={f}>{f}</span>
          ))}
        </div>
      )}
      {open && (
        <Suspense fallback={<pre className="mg-sql-code"><code>{source.sql}</code></pre>}>
          <SqlCode sql={source.sql} label={source.title} />
        </Suspense>
      )}
    </article>
  );
}
