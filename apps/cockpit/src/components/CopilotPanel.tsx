import { useEffect, useRef, useState, type RefObject } from 'react';
import { ArrowUp, Bot, ChevronDown, ChevronUp, Database, Loader2, Maximize2, Minimize2, RotateCcw } from 'lucide-react';
import clsx from 'clsx';
import { ask, runSql, type SqlResult, WrenError } from '../lib/wren';

type Msg =
  | { role: 'user'; text: string; at: string }
  | { role: 'assistant'; text: string; sql?: string; result?: SqlResult; error?: string; at: string; pending?: boolean };

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

  useEffect(() => {
    listRef.current?.scrollTo({ top: listRef.current.scrollHeight, behavior: 'smooth' });
  }, [msgs]);

  async function send(question: string) {
    const q = question.trim();
    if (!q || busy) return;
    setInput('');
    setBusy(true);
    setMsgs((m) => [...m, { role: 'user', text: q, at: now() }, { role: 'assistant', text: 'Logo modelleri üstünde SQL üretiliyor…', at: now(), pending: true }]);
    try {
      const a = await ask(q, threadId);
      if (a.threadId) setThreadId(a.threadId);
      let result: SqlResult | undefined;
      if (a.sql) result = await runSql(a.sql, 50);
      const text =
        a.summary?.trim() ||
        (result ? `${result.totalRows} satır döndü.` : (a.explanation?.trim() || 'Motor bu soru için SQL üretmedi.'));
      setMsgs((m) => [...m.slice(0, -1), { role: 'assistant', text, sql: a.sql, result, at: now() }]);
    } catch (e) {
      const msg = e instanceof WrenError ? `${e.message}${e.code ? ` (${e.code})` : ''}` : e instanceof Error ? e.message : String(e);
      setMsgs((m) => [...m.slice(0, -1), { role: 'assistant', text: 'Soru yanıtlanamadı.', error: msg, at: now() }]);
    } finally {
      setBusy(false);
    }
  }

  return (
    <aside className={clsx('card flex h-full min-h-[560px] w-full flex-col overflow-hidden lg:shrink-0', wide ? 'lg:w-[560px]' : 'lg:w-[330px]')}>
      <div className="flex items-center gap-3 border-b border-line px-4 py-3">
        <div className="grid h-9 w-9 place-items-center rounded-xl bg-brand text-white">
          <Bot size={18} />
        </div>
        <div className="min-w-0 flex-1 leading-tight">
          <div className="flex items-center gap-2">
            <span className="font-display text-[15px] font-semibold">Finans Copilotu</span>
            <span className="rounded-md bg-page px-1.5 py-0.5 text-[10px] font-bold text-ink-muted">NL→SQL</span>
          </div>
          <div className="flex items-center gap-1.5 text-[11px] text-ink-muted">
            <span className={clsx('h-1.5 w-1.5 rounded-full', engineOk ? 'bg-ok' : engineOk === false ? 'bg-warn' : 'bg-ink-faint')} />
            {engineOk ? 'Logo ERP modelleri canlı' : engineOk === false ? 'Model deploy bekliyor' : 'Bağlantı kontrol ediliyor'}
          </div>
        </div>
        <button type="button" className="text-ink-faint hover:text-ink" title="Yeni sohbet" onClick={() => { setMsgs([]); setThreadId(undefined); }}>
          <RotateCcw size={15} />
        </button>
        <button type="button" className="text-ink-faint hover:text-ink" title={wide ? 'Daralt' : 'Genişlet'} aria-pressed={wide} onClick={() => setWide((v) => !v)}>
          {wide ? <Minimize2 size={15} /> : <Maximize2 size={15} />}
        </button>
      </div>

      <div className="mx-4 mt-3 rounded-xl bg-page px-3 py-2 text-[11px] text-ink-muted">
        <span className="font-semibold text-ink">Aktif bağlam:</span> Logo Tiger · fatura, malzeme hareketi, cari, sipariş modelleri (2026). Cevaplar deterministik SQL ile üretilir; SQL her yanıtta görünür.
      </div>

      <div ref={listRef} className="scroll-thin flex-1 space-y-3 overflow-y-auto px-4 py-3">
        {msgs.length === 0 && (
          <div className="pt-2 text-[12px] text-ink-muted">
            Logo verisine Türkçe soru sorun. Örnek:
            <div className="mt-2 flex flex-wrap gap-1.5">
              {SUGGESTIONS.map((s) => (
                <button key={s} onClick={() => send(s)} className="chip hover:border-brand hover:text-brand">
                  {s}
                </button>
              ))}
            </div>
          </div>
        )}
        {msgs.map((m, i) => (m.role === 'user' ? <UserBubble key={i} m={m} /> : <AssistantCard key={i} m={m} wide={wide} />))}
      </div>

      {msgs.length > 0 && (
        <div className="flex gap-1.5 overflow-x-auto px-4 pb-2 scroll-thin">
          {SUGGESTIONS.map((s) => (
            <button key={s} onClick={() => send(s)} disabled={busy} className="chip shrink-0 hover:border-brand hover:text-brand disabled:opacity-50">
              {s}
            </button>
          ))}
        </div>
      )}

      <form
        className="border-t border-line p-3"
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
          <span className="inline-flex items-center gap-1"><Database size={11} /> Salt-okunur · LOGO_DB</span>
          <span>Enter ile gönder</span>
        </div>
      </form>
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

function AssistantCard({ m, wide }: { m: Extract<Msg, { role: 'assistant' }>; wide?: boolean }) {
  const [showSql, setShowSql] = useState(false);
  const cols = m.result?.columns.slice(0, wide ? 8 : 5) ?? [];
  const rows = m.result?.records.slice(0, wide ? 20 : 8) ?? [];
  return (
    <div className="rounded-2xl border border-line bg-white p-3">
      <div className="flex items-center gap-2 text-[11px] font-semibold text-ink-muted">
        {m.pending ? <Loader2 size={12} className="animate-spin text-brand" /> : <Bot size={12} className="text-brand" />}
        Copilot · {m.at}
      </div>
      <p className={clsx('mt-1.5 text-[13px] leading-snug', m.error && 'text-brand-accent')}>{m.text}</p>
      {m.error && <pre className="mt-1 whitespace-pre-wrap break-words rounded-lg bg-page p-2 text-[10px] text-ink-muted">{m.error}</pre>}
      {rows.length > 0 && (
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
          {m.result && m.result.totalRows > rows.length && (
            <div className="bg-page px-2 py-1 text-[10px] text-ink-muted">İlk {rows.length} / {m.result.totalRows} satır</div>
          )}
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
    </div>
  );
}

function fmtCell(v: unknown): string {
  if (v == null) return '';
  if (typeof v === 'number') return new Intl.NumberFormat('tr-TR', { maximumFractionDigits: 2 }).format(v);
  return String(v);
}
