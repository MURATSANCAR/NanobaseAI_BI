import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { AlertTriangle, Check, ChevronDown, ChevronLeft, ChevronRight, KeyRound, Link2, Lock, Pencil, Search, Sparkles, X } from 'lucide-react';
import clsx from 'clsx';
import { acceptSuggestion, catalogTable, catalogTables, dismissSuggestion, rewriteLabel, writeLabel, type CatalogColumn, type CatalogTable } from '../lib/engine';

/** Veri sözlüğü: taramada bulunan tablolar, kolonları ve aralarındaki ilişkiler.
 *
 *  Buradaki her satırın üç ayrı okuması olabilir ve hiçbiri diğerini ezmez — kaynağın kendi yorumu,
 *  bu sistemin veriden çıkardığı, ve bir kişinin buraya yazdığı. Yazılan kazanır; sorulara verilen
 *  cevaplar doğrudan ondan gider. Yanlış bir etiket, eksik bir etiketten kötüdür: düzeltilebilir. */

const STATUS: Record<string, { label: string; cls: string }> = {
  CERTIFIED: { label: 'tanımlı', cls: 'bg-ok/15 text-ok' },
  CANDIDATE: { label: 'aday', cls: 'bg-[#C98A1E]/15 text-[#8a5f12]' },
  DESCRIBED: { label: 'açıklamalı', cls: 'bg-brand-soft text-brand-deep' },
  UNDEFINED: { label: 'tanımsız', cls: 'bg-line text-ink-faint' },
};

function nf(n?: number | null) {
  return n == null ? '—' : n.toLocaleString('tr-TR');
}

const PAGE = 40;

export function CatalogExplorer() {
  const [search, setSearch] = useState('');
  const [page, setPage] = useState(0);
  const [open, setOpen] = useState<string | null>(null);
  const list = useQuery({
    queryKey: ['catalog-tables', search, page],
    queryFn: () => catalogTables(search, PAGE, page * PAGE),
    staleTime: 5 * 60_000,
  });
  const total = list.data?.total ?? 0;
  const pages = Math.max(1, Math.ceil(total / PAGE));
  const from = total ? page * PAGE + 1 : 0;
  const to = Math.min(total, (page + 1) * PAGE);
  const go = (p: number) => { setPage(p); setOpen(null); window.scrollTo({ top: 0, behavior: 'smooth' }); };

  return (
    <div className="space-y-4">
      <div className="card p-4 sm:p-5">
        <h1 className="font-display text-lg font-semibold text-ink">Veri Sözlüğü</h1>
        <p className="mt-1 text-[13px] text-ink-muted">
          Taramada bulunan tablolar, kolonlar ve ilişkileri. Bir kolonun ne anlama geldiğini buraya yazarsanız
          cevaplar doğrudan sizin tanımınızdan gider.
        </p>

        {list.data?.warning ? (
          <div className="mt-3 flex items-start gap-2 rounded-xl border border-brand-accent/40 bg-brand-accent/5 p-3 text-[13px]">
            <AlertTriangle size={16} className="mt-0.5 shrink-0 text-brand-accent" />
            <span>{list.data.warning}</span>
          </div>
        ) : null}

        <div className="relative mt-3">
          <Search size={15} className="pointer-events-none absolute left-3 top-2.5 text-ink-faint" />
          <input
            value={search}
            onChange={(e) => { setSearch(e.target.value); setPage(0); }}
            placeholder="Tablo ya da kolon ara — fatura, TRCODE, müşteri…"
            className="w-full rounded-xl border border-line bg-white py-2 pl-9 pr-3 text-sm outline-none focus:border-brand"
          />
        </div>

        {list.data ? (
          <div className="mt-3 flex flex-wrap items-center gap-3 border-t border-line pt-3">
            <span className="text-[13px] text-ink">
              <span className="font-semibold">{nf(total)}</span> tablo{search.trim() ? ' eşleşti' : ''}
            </span>
            <span className="text-[11px] text-ink-faint">en dolu tablodan en boşa doğru</span>
            <span className="ml-auto flex items-center gap-1.5">
              <span className="mr-1 text-[11px] text-ink-muted">{nf(from)}–{nf(to)}</span>
              <Pager label="Önceki" icon={ChevronLeft} disabled={page === 0} onClick={() => go(page - 1)} />
              <span className="min-w-[52px] text-center text-[11px] text-ink-faint">{page + 1} / {nf(pages)}</span>
              <Pager label="Sonraki" icon={ChevronRight} disabled={page + 1 >= pages} onClick={() => go(page + 1)} />
            </span>
          </div>
        ) : null}
      </div>

      {list.isPending ? <div className="card p-4 text-sm text-ink-muted">Sözlük hazırlanıyor…</div> : null}
      {list.isError ? (
        <div className="card flex items-start gap-2 border-brand-accent/40 p-4 text-sm">
          <AlertTriangle size={16} className="mt-0.5 shrink-0 text-brand-accent" />
          <span>Sözlük okunamadı: {(list.error as Error).message}</span>
        </div>
      ) : null}

      <div className="space-y-2">
        {(list.data?.tables ?? []).map((t) => (
          <TableRow key={t.tableName} t={t} open={open === t.tableName} onToggle={() => setOpen(open === t.tableName ? null : t.tableName)} />
        ))}
      </div>

      {pages > 1 ? (
        <div className="flex items-center justify-center gap-2 pb-2">
          <Pager label="Önceki" icon={ChevronLeft} disabled={page === 0} onClick={() => go(page - 1)} />
          <span className="text-[12px] text-ink-muted">{page + 1} / {nf(pages)}</span>
          <Pager label="Sonraki" icon={ChevronRight} disabled={page + 1 >= pages} onClick={() => go(page + 1)} />
        </div>
      ) : null}
    </div>
  );
}

function Pager({ label, icon: Icon, disabled, onClick }: { label: string; icon: typeof ChevronRight; disabled: boolean; onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      aria-label={label}
      className="inline-flex items-center gap-1 rounded-lg border border-line bg-white px-2 py-1 text-[11px] text-ink-muted transition hover:border-brand hover:text-brand disabled:opacity-35 disabled:hover:border-line disabled:hover:text-ink-muted"
    >
      {label === 'Önceki' ? <Icon size={12} /> : null}
      <span className="hidden sm:inline">{label}</span>
      {label === 'Sonraki' ? <Icon size={12} /> : null}
    </button>
  );
}

function TableRow({ t, open, onToggle }: { t: CatalogTable; open: boolean; onToggle: () => void }) {
  // kolonlar ancak tablo açıldığında istenir — hepsini birden çekmek sekiz megabayt eder
  const detail = useQuery({
    queryKey: ['catalog-table', t.entity],
    queryFn: () => catalogTable(t.entity),
    enabled: open,
    staleTime: 5 * 60_000,
  });
  const full = detail.data?.tables?.[0];

  return (
    <div className="card overflow-hidden">
      <button type="button" onClick={onToggle} className="flex w-full items-center gap-3 px-4 py-3 text-left hover:bg-rail">
        {open ? <ChevronDown size={16} className="shrink-0 text-ink-faint" /> : <ChevronRight size={16} className="shrink-0 text-ink-faint" />}
        <span className="min-w-0 flex-1">
          <span className="block truncate text-[14px] font-semibold text-ink">{t.entity}</span>
          <span className="block truncate text-[11px] text-ink-faint">{t.tableName}</span>
        </span>
        <span className="hidden shrink-0 text-right text-[11px] text-ink-muted sm:block">
          {nf(t.rowCount)} satır · {t.columnCount} kolon
          {t.relationships.length ? ` · ${t.relationships.length} ilişki` : ''}
        </span>
        {t.undefinedColumns ? (
          <span className="shrink-0 rounded-md bg-line px-1.5 py-0.5 text-[10px] text-ink-faint">{t.undefinedColumns} tanımsız</span>
        ) : null}
      </button>

      {open ? (
        <div className="border-t border-line bg-rail/40 px-4 py-3">
          <LabelBox tablePattern={t.tablePattern} column={null} current={full?.annotations?.[0]} source={full?.description ?? t.description} what="Bu tablo" />

          {(full?.relationships ?? t.relationships).length ? (
            <div className="mt-3">
              <div className="eyebrow mb-1.5">İlişkiler</div>
              <div className="flex flex-wrap gap-1.5">
                {(full?.relationships ?? t.relationships).map((r, i) => (
                  <span key={i} className="inline-flex items-center gap-1 rounded-lg border border-line bg-white px-2 py-1 text-[11px]">
                    <Link2 size={11} className="text-ink-faint" />
                    <span className="font-medium">{r.column}</span>
                    <span className="text-ink-faint">→</span>
                    <span>{r.ref_entity}.{r.ref_column}</span>
                  </span>
                ))}
              </div>
            </div>
          ) : null}

          <div className="mt-3">
            <div className="eyebrow mb-1.5">Kolonlar</div>
            {detail.isPending ? <div className="text-[13px] text-ink-muted">Kolonlar getiriliyor…</div> : null}
            <div className="space-y-1.5">
              {(full?.columns ?? []).map((c) => (
                <ColumnRow key={c.name} c={c} tablePattern={t.tablePattern} entity={t.entity} />
              ))}
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}

function ColumnRow({ c, tablePattern, entity }: { c: CatalogColumn; tablePattern: string; entity: string }) {
  const st = STATUS[c.status] ?? STATUS.UNDEFINED;
  const derived = (c.derived ?? []).filter((d) => d.source !== 'freshness');
  const measured = (c.derived ?? []).filter((d) => d.source === 'freshness');

  return (
    <div className="rounded-xl border border-line bg-white px-3 py-2">
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-mono text-[12px] font-semibold text-ink">{c.name}</span>
        <span className="text-[11px] text-ink-faint">{c.type}</span>
        {c.isPrimaryKey ? <KeyRound size={11} className="text-[#C98A1E]" /> : null}
        {c.ref ? (
          <span className="inline-flex items-center gap-1 text-[11px] text-ink-muted"><Link2 size={11} /> {c.ref}</span>
        ) : null}
        {c.sensitive ? (
          <span className="inline-flex items-center gap-1 rounded-md bg-brand-accent/10 px-1.5 py-0.5 text-[10px] text-brand-accent">
            <Lock size={10} /> kişisel veri
          </span>
        ) : null}
        <span className={clsx('rounded-md px-1.5 py-0.5 text-[10px] font-medium', st.cls)}>{st.label}</span>
        {/* a join is a fact about the table, not a name for this column: it has its own section */}
        {c.concepts.filter((x) => x.type !== 'RELATIONSHIP').slice(0, 3).map((x) => (
          <span key={x.id} className="rounded-md bg-brand-soft px-1.5 py-0.5 text-[10px] text-brand-deep" title={x.formula ?? (x.values ?? []).join(', ')}>
            “{x.term}”
          </span>
        ))}
      </div>

      {/* değerler yalnız kişisel veri olmayan kolonlarda gösterilir */}
      {!c.sensitive && (c.topValues ?? []).length ? (
        <div className="mt-1 truncate text-[11px] text-ink-faint">
          değerler: {(c.topValues ?? []).slice(0, 8).map(([v]) => v || '(boş)').join(', ')}
          {c.distinct ? ` · ${nf(c.distinct)} farklı` : ''}
        </div>
      ) : null}

      {c.description ? <Note tone="kaynak" text={c.description} /> : null}
      {derived.map((d, i) => <Note key={i} tone="çıkarım" text={d.text} />)}
      {measured.map((d, i) => <Note key={`m${i}`} tone="ölçüm" text={d.text} />)}

      {c.suggestion && !c.annotations?.length ? <SuggestionRow s={c.suggestion} /> : null}
      <LabelBox tablePattern={tablePattern} column={c.name} current={c.annotations?.[0]} source={c.description} what={`${entity}.${c.name}`} compact />
    </div>
  );
}

/** Sistemin kendi okuması. Kabul edilene kadar tanım değildir; kabul etmek kişinin işidir. */
function SuggestionRow({ s }: { s: NonNullable<CatalogColumn['suggestion']> }) {
  const qc = useQueryClient();
  const [busy, setBusy] = useState<'accept' | 'dismiss' | null>(null);
  const after = async () => {
    await Promise.all([
      qc.refetchQueries({ queryKey: ['catalog-table'], type: 'active' }),
      qc.invalidateQueries({ queryKey: ['catalog-tables'] }),
    ]);
    setBusy(null);
  };
  return (
    <div className="mt-1.5 flex flex-wrap items-start gap-1.5 rounded-lg border border-dashed border-brand/30 bg-brand-soft/40 px-2 py-1.5 text-[11px]">
      <span className="mt-px inline-flex shrink-0 items-center gap-1 rounded bg-white px-1 text-[10px] text-brand-deep">
        <Sparkles size={9} /> öneri
      </span>
      <span className="min-w-0 flex-1 text-ink">{s.text}</span>
      <span className="flex shrink-0 items-center gap-1">
        <button
          type="button"
          disabled={busy !== null}
          onClick={() => { setBusy('accept'); void acceptSuggestion(s.id).then(after).catch(() => setBusy(null)); }}
          className="inline-flex items-center gap-1 rounded-md bg-brand px-1.5 py-0.5 text-[10px] font-medium text-white disabled:opacity-50"
        >
          <Check size={10} /> {busy === 'accept' ? '…' : 'kabul et'}
        </button>
        <button
          type="button"
          disabled={busy !== null}
          onClick={() => { setBusy('dismiss'); void dismissSuggestion(s.id).then(after).catch(() => setBusy(null)); }}
          className="inline-flex items-center gap-1 rounded-md border border-line bg-white px-1.5 py-0.5 text-[10px] text-ink-muted disabled:opacity-50"
        >
          <X size={10} /> yanlış
        </button>
      </span>
    </div>
  );
}

function Note({ tone, text }: { tone: string; text: string }) {
  const cls = tone === 'kaynak' ? 'bg-line text-ink-muted' : tone === 'ölçüm' ? 'bg-ok/10 text-ok' : 'bg-brand-soft text-brand-deep';
  return (
    <div className="mt-1 flex items-start gap-1.5 text-[11px] text-ink-muted">
      <span className={clsx('mt-px shrink-0 rounded px-1 text-[10px]', cls)}>{tone}</span>
      <span className="min-w-0 flex-1">{text}</span>
    </div>
  );
}

/** Kişinin yazdığı tanım. Varsa düzeltilebilir: eskisi silinmez, geri çekilir; modele yalnız yenisi gider. */
function LabelBox({
  tablePattern, column, current, source, what, compact,
}: {
  tablePattern: string;
  column: string | null;
  current?: { id: string; text: string; author: string };
  source?: string | null;
  what: string;
  compact?: boolean;
}) {
  const qc = useQueryClient();
  const [editing, setEditing] = useState(false);
  const [text, setText] = useState(current?.text ?? '');
  const [err, setErr] = useState<string | null>(null);

  const save = useMutation({
    mutationFn: () => (current ? rewriteLabel(current.id, tablePattern, column, text.trim()) : writeLabel(tablePattern, column, text.trim())),
    onSuccess: async () => {
      setEditing(false);
      setErr(null);
      // what someone just wrote has to appear where they wrote it, without a reload
      await Promise.all([
        qc.refetchQueries({ queryKey: ['catalog-table'], type: 'active' }),
        qc.invalidateQueries({ queryKey: ['catalog-tables'] }),
      ]);
    },
    onError: (e: Error) => setErr(e.message),
  });

  if (!editing) {
    return (
      <div className={clsx('flex items-start gap-1.5 text-[11px]', compact ? 'mt-1' : 'mt-0')}>
        {current ? (
          <>
            <span className="mt-px shrink-0 rounded bg-brand px-1 text-[10px] text-white">tanım</span>
            <span className="min-w-0 flex-1 text-ink">{current.text} <span className="text-ink-faint">— {current.author}</span></span>
          </>
        ) : (
          <span className="min-w-0 flex-1 text-ink-faint">
            {source ? 'Bu açıklama kaynaktan geliyor; kendi tanımınızı yazabilirsiniz.' : `${what} için henüz bir tanım yazılmamış.`}
          </span>
        )}
        <button
          type="button"
          onClick={() => { setText(current?.text ?? ''); setEditing(true); }}
          className="inline-flex shrink-0 items-center gap-1 rounded-md border border-line px-1.5 py-0.5 text-[10px] text-ink-muted hover:border-brand hover:text-brand"
        >
          <Pencil size={10} /> {current ? 'düzelt' : 'tanım yaz'}
        </button>
      </div>
    );
  }

  return (
    <div className="mt-1.5">
      <textarea
        value={text}
        onChange={(e) => setText(e.target.value)}
        rows={2}
        autoFocus
        placeholder={column ? 'Örn: 8 = toptan, 7 = perakende — ya da kolonun ne anlama geldiği' : 'Bu tablonun ne tuttuğu'}
        className="w-full rounded-lg border border-line bg-white p-2 text-[12px] outline-none focus:border-brand"
      />
      <div className="mt-1 flex items-center gap-2">
        <button
          type="button"
          disabled={!text.trim() || save.isPending}
          onClick={() => save.mutate()}
          className="inline-flex items-center gap-1 rounded-md bg-brand px-2 py-1 text-[11px] font-medium text-white disabled:opacity-50"
        >
          <Check size={11} /> {save.isPending ? 'kaydediliyor…' : 'kaydet'}
        </button>
        <button type="button" onClick={() => { setEditing(false); setErr(null); }} className="inline-flex items-center gap-1 text-[11px] text-ink-muted">
          <X size={11} /> vazgeç
        </button>
        <span className="text-[10px] text-ink-faint">Yazdığınız tanım, veriyle örtüşürse doğrudan cevaplarda kullanılır.</span>
      </div>
      {err ? <div className="mt-1 text-[11px] text-brand-accent">{err}</div> : null}
    </div>
  );
}
