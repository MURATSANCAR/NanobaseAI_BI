import { useEffect, useRef, useState, type RefObject } from 'react';
import { ArrowUp, Bot, ChevronDown, ChevronUp, Database, Loader2, Maximize2, Minimize2, RotateCcw, ShieldCheck, ThumbsDown, ThumbsUp } from 'lucide-react';
import clsx from 'clsx';
import { ask, runSql, sendFeedback, type SemanticTrace, type SqlResult, EngineError } from '../lib/engine';
import { ResultChart } from './ResultChart';
import { Thinking } from './Thinking';

type Msg =
  | { role: 'user'; text: string; at: string }
  | {
      role: 'assistant';
      text: string;
      sql?: string;
      result?: SqlResult;
      error?: string;
      at: string;
      pending?: boolean;
      semantic?: SemanticTrace;
      queryId?: string;
    };

const SUGGESTIONS = [
  '2026 kanal bazında net ciro',
  'En çok iade alan 10 müşteri',
  'Aylık iskonto oranı',
  'En çok satan 10 kitap (adet)',
];

const now = () => new Date().toLocaleTimeString('tr-TR', { hour: '2-digit', minute: '2-digit' });

export function CopilotPanel({ engineOk, inputRef }: { engineOk: boolean | null; inputRef?: RefObject<HTMLInputElement> }) {
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [wide, setWide] = useState(false);
  const [input, setInput] = useState('');
  const [busy, setBusy] = useState(false);
  const [threadId, setThreadId] = useState<string | undefined>();
  const listRef = useRef<HTMLDivElement>(null);

  // Giriş kutusu panelin üstünde; yeni mesaj gelince listenin başına kaydır ki cevap hemen kutunun altında görünsün.
  useEffect(() => {
    listRef.current?.scrollTo({ top: 0, behavior: 'smooth' });
  }, [msgs]);

  async function send(question: string) {
    const q = question.trim();
    if (!q || busy) return;
    setInput('');
    setBusy(true);
    setMsgs((m) => [...m, { role: 'user', text: q, at: now() }, { role: 'assistant', text: '', at: now(), pending: true }]);
    try {
      const a = await ask(q, threadId);
      if (a.threadId) setThreadId(a.threadId);
      let result: SqlResult | undefined;
      if (a.sql) result = await runSql(a.sql, 50, q);
      const text =
        a.summary?.trim() ||
        (result ? `${result.totalRows} satır döndü.` : (a.explanation?.trim() || 'Motor bu soru için SQL üretmedi.'));
      setMsgs((m) => [
        ...m.slice(0, -1),
        { role: 'assistant', text, sql: a.sql, result, at: now(), semantic: a.semantic, queryId: a.queryId },
      ]);
    } catch (e) {
      const msg = e instanceof EngineError ? `${e.message}${e.code ? ` (${e.code})` : ''}` : e instanceof Error ? e.message : String(e);
      setMsgs((m) => [...m.slice(0, -1), { role: 'assistant', text: 'Soru yanıtlanamadı.', error: msg, at: now() }]);
    } finally {
      setBusy(false);
    }
  }

  return (
    <aside className={clsx('card flex h-full min-h-[420px] w-full flex-col overflow-hidden sm:min-h-[560px] lg:shrink-0', wide ? 'lg:w-[560px]' : 'lg:w-[330px]')}>
      <div className="flex items-center gap-3 border-b border-line px-4 py-3">
        <div className="grid h-9 w-9 place-items-center rounded-xl bg-brand text-white">
          <Bot size={18} />
        </div>
        <div className="min-w-0 flex-1 leading-tight">
          <div className="flex items-center gap-2">
            <span className="font-display text-[15px] font-semibold">Timaş Finans</span>
            <span className="rounded-md bg-page px-1.5 py-0.5 text-[10px] font-bold text-ink-muted">NL→SQL</span>
          </div>
          <div className="flex items-center gap-1.5 text-[11px] text-ink-muted">
            <span className={clsx('h-1.5 w-1.5 rounded-full', engineOk ? 'bg-ok' : engineOk === false ? 'bg-warn' : 'bg-ink-faint')} />
            {engineOk ? 'Veri modelleri canlı' : engineOk === false ? 'Model deploy bekliyor' : 'Bağlantı kontrol ediliyor'}
          </div>
        </div>
        <button type="button" className="text-ink-faint hover:text-ink" title="Yeni sohbet" onClick={() => { setMsgs([]); setThreadId(undefined); }}>
          <RotateCcw size={15} />
        </button>
        <button type="button" className="hidden text-ink-faint hover:text-ink lg:block" title={wide ? 'Daralt' : 'Genişlet'} aria-pressed={wide} onClick={() => setWide((v) => !v)}>
          {wide ? <Minimize2 size={15} /> : <Maximize2 size={15} />}
        </button>
      </div>

      <form
        className="border-b border-line px-4 pb-3 pt-3"
        onSubmit={(e) => {
          e.preventDefault();
          void send(input);
        }}
      >
        <div className="flex items-center gap-2 rounded-xl border border-line bg-white px-3 py-2 focus-within:border-brand">
          <input
            ref={inputRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Finansal veriyle konuş…"
            className="min-w-0 flex-1 bg-transparent text-[13px] outline-none placeholder:text-ink-faint"
            disabled={busy}
          />
          <button type="submit" disabled={busy || !input.trim()} className="grid h-8 w-8 place-items-center rounded-lg bg-brand text-white disabled:opacity-40">
            {busy ? <Loader2 size={15} className="animate-spin" /> : <ArrowUp size={15} />}
          </button>
        </div>
        <div className="mt-2 flex items-center justify-between text-[10px] text-ink-muted">
          <span className="inline-flex items-center gap-1"><Database size={11} /> Salt-okunur</span>
          <span className="hidden sm:inline">Enter ile gönder</span>
        </div>
      </form>
      <div className="mx-4 mt-3 rounded-xl bg-page px-3 py-2 text-[11px] text-ink-muted">
        <span className="font-semibold text-ink">Aktif bağlam:</span> fatura, malzeme hareketi, cari ve sipariş modelleri. Cevaplar deterministik SQL ile üretilir; SQL her yanıtta görünür.
      </div>

      <div ref={listRef} className="scroll-thin flex-1 space-y-3 overflow-y-auto px-4 py-3">
        {msgs.length === 0 && (
          <div className="pt-2 text-[12px] text-ink-muted">
            Verilerinize Türkçe soru sorun. Örnek:
            <div className="mt-2 flex flex-wrap gap-1.5">
              {SUGGESTIONS.map((s) => (
                <button key={s} onClick={() => send(s)} className="chip hover:border-brand hover:text-brand">
                  {s}
                </button>
              ))}
            </div>
          </div>
        )}
        {[...msgs].reverse().map((m, i) =>
          m.role === 'user' ? <UserBubble key={i} m={m} /> : m.pending ? <Thinking key={i} /> : <AssistantCard key={i} m={m} wide={wide} />,
        )}
      </div>


    </aside>
  );
}

function UserBubble({ m }: { m: Extract<Msg, { role: 'user' }> }) {
  return (
    <div className="flex flex-col items-end">
      <div className="max-w-[92%] rounded-2xl rounded-br-md bg-brand px-3.5 py-2.5 text-[13px] leading-snug text-white">{m.text}</div>
      <div className="mt-1 text-[10px] text-ink-faint">Siz · {m.at}</div>
    </div>
  );
}

/** Anlam izi: hangi terim hangi fiziksel karşılığa çözümlendi, hangi derleyici üretti, kaç kanıt var.
 *  Katalogda karşılığı olmayan terimler ayrıca gösterilir — cevabın neden öyle olduğu görünür olsun. */
function SemanticTraceCard({ trace }: { trace: SemanticTrace }) {
  const [open, setOpen] = useState(false);
  const slots = trace.query?.slots ?? [];
  const unresolved = trace.query?.unresolved ?? [];
  const certified = trace.certified === true;
  const compilerLabel =
    trace.compiler === 'deterministic' ? 'katalogdan doğrudan' : trace.compiler === 'existing_llm' ? 'model destekli' : trace.compiler ?? '—';
  if (slots.length === 0 && unresolved.length === 0) return null;
  return (
    <div className="mt-2">
      <button onClick={() => setOpen((v) => !v)} className="inline-flex items-center gap-1 text-[11px] font-semibold text-brand">
        {open ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
        <ShieldCheck size={12} className={certified ? 'text-ok' : 'text-ink-faint'} />
        Anlam ({compilerLabel}
        {trace.catalogVersion ? ` · katalog v${trace.catalogVersion}` : ''})
      </button>
      {open && (
        <div className="mt-1 space-y-1 rounded-lg bg-page p-2 text-[11px] text-ink-muted">
          {slots.map((s, i) => {
            const map = (s.mapping ?? {}) as { entity?: string; column?: string; values?: string[]; formula?: string };
            const target = map.formula
              ? String(map.formula)
              : `${map.entity ?? ''}.${map.column ?? ''}${map.values?.length ? ` ∈ (${map.values.join(', ')})` : ''}`;
            return (
              <div key={i} className="flex flex-wrap items-baseline gap-1">
                <span className="font-semibold text-ink">“{s.term}”</span>
                <span>→</span>
                <span className="font-mono text-[10px] text-ink">{target}</span>
                <span className={clsx('rounded px-1 text-[9px] font-bold', s.status === 'CERTIFIED' ? 'bg-ok/15 text-ok' : 'bg-ink-faint/15')}>
                  {s.status}
                </span>
              </div>
            );
          })}
          {unresolved.length > 0 && (
            <div className="text-brand-accent">Katalogda karşılığı yok: {unresolved.join(', ')}</div>
          )}
          {(trace.query?.explanation ?? []).slice(-2).map((line, i) => (
            <div key={`x${i}`} className="text-[10px]">{line}</div>
          ))}
        </div>
      )}
    </div>
  );
}

/** "Doğru/yanlış" işareti köprüye gider (sl_query_log.validated); gece madenciliği bunu kanıt sayar. */
function FeedbackRow({ queryId }: { queryId: string }) {
  const [sent, setSent] = useState<null | boolean>(null);
  const [failed, setFailed] = useState(false);
  const mark = async (ok: boolean) => {
    setSent(ok);
    try {
      await sendFeedback(queryId, ok);
    } catch {
      setFailed(true);
    }
  };
  if (sent !== null) {
    return (
      <div className="mt-2 text-[10px] text-ink-muted">
        {failed ? 'Geri bildirim gönderilemedi.' : sent ? 'Teşekkürler — bu cevap doğrulanmış örnek olarak kaydedildi.' : 'Kaydedildi; bu eşleme gözden geçirilecek.'}
      </div>
    );
  }
  return (
    <div className="mt-2 flex items-center gap-2 text-[10px] text-ink-muted">
      <span>Bu cevap doğru mu?</span>
      <button onClick={() => mark(true)} className="inline-flex items-center gap-1 rounded-md border border-line px-1.5 py-0.5 hover:border-ok hover:text-ok">
        <ThumbsUp size={11} /> Doğru
      </button>
      <button onClick={() => mark(false)} className="inline-flex items-center gap-1 rounded-md border border-line px-1.5 py-0.5 hover:border-brand-accent hover:text-brand-accent">
        <ThumbsDown size={11} /> Yanlış
      </button>
    </div>
  );
}

function AssistantCard({ m, wide }: { m: Extract<Msg, { role: 'assistant' }>; wide?: boolean }) {
  const [showSql, setShowSql] = useState(false);
  const [showTable, setShowTable] = useState(false);
  const cols = m.result?.columns.slice(0, wide ? 8 : 5) ?? [];
  const rows = m.result?.records.slice(0, wide ? 20 : 8) ?? [];
  const widget = m.result?.widget;
  // Grafik çizilebiliyorsa tablo katlanır; çizilemiyorsa (table tipi ya da uygunsuz veri) eskisi gibi açık gelir.
  const chart =
    widget && widget.type !== 'table' && m.result ? (
      <ResultChart widget={widget} records={m.result.records} wide={wide} />
    ) : null;
  return (
    <div className="rounded-2xl border border-line bg-white p-3">
      <div className="flex items-center gap-2 text-[11px] font-semibold text-ink-muted">
        {m.pending ? <Loader2 size={12} className="animate-spin text-brand" /> : <Bot size={12} className="text-brand" />}
        Timaş Finans · {m.at}
      </div>
      <p className={clsx('mt-1.5 text-[13px] leading-snug', m.error && 'text-brand-accent')}>{m.text}</p>
      {m.error && <pre className="mt-1 whitespace-pre-wrap break-words rounded-lg bg-page p-2 text-[10px] text-ink-muted">{m.error}</pre>}
      {chart}
      {rows.length > 0 && !chart && <ResultTable cols={cols} rows={rows} totalRows={m.result?.totalRows ?? rows.length} />}
      {rows.length > 0 && chart && (
        <div className="mt-2">
          <button onClick={() => setShowTable((v) => !v)} className="inline-flex items-center gap-1 text-[11px] font-semibold text-brand">
            {showTable ? <ChevronUp size={12} /> : <ChevronDown size={12} />} Tablo ({m.result?.totalRows ?? rows.length} satır)
          </button>
          {showTable && <ResultTable cols={cols} rows={rows} totalRows={m.result?.totalRows ?? rows.length} />}
        </div>
      )}
      {m.sql && (
        <div className="mt-2">
          <button onClick={() => setShowSql((v) => !v)} className="inline-flex items-center gap-1 text-[11px] font-semibold text-brand">
            {showSql ? <ChevronUp size={12} /> : <ChevronDown size={12} />} Üretilen SQL
          </button>
          {showSql && <pre className="mt-1 max-h-48 overflow-auto scroll-thin whitespace-pre-wrap break-words rounded-lg bg-ink p-2 text-[10px] text-white/90">{m.sql}</pre>}
        </div>
      )}
      {m.semantic && <SemanticTraceCard trace={m.semantic} />}
      {m.queryId && !m.error && <FeedbackRow queryId={m.queryId} />}
    </div>
  );
}

function ResultTable({
  cols,
  rows,
  totalRows,
}: {
  cols: { name: string; type: string }[];
  rows: Record<string, unknown>[];
  totalRows: number;
}) {
  return (
    <div className="mt-2 overflow-x-auto scroll-thin rounded-lg border border-line">
      <table className="w-full text-[11px]">
        <thead className="bg-page">
          <tr>{cols.map((c) => <th key={c.name} className="px-2 py-1 text-left font-semibold">{c.name}</th>)}</tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i} className="border-t border-line/60">
              {cols.map((c) => <td key={c.name} className="whitespace-nowrap px-2 py-1">{fmtCell(r[c.name])}</td>)}
            </tr>
          ))}
        </tbody>
      </table>
      {totalRows > rows.length && (
        <div className="bg-page px-2 py-1 text-[10px] text-ink-muted">İlk {rows.length} / {totalRows} satır</div>
      )}
    </div>
  );
}

function fmtCell(v: unknown): string {
  if (v == null) return '';
  if (typeof v === 'number') return new Intl.NumberFormat('tr-TR', { maximumFractionDigits: 2 }).format(v);
  return String(v);
}
