import { type ChatModule } from '../lib/chatModules';
import { useEffect, useRef, useState, type RefObject } from 'react';
import { ArrowUp, Bot, Check, ChevronDown, ChevronUp, Database, FileSpreadsheet, LayoutDashboard, Loader2, Maximize2, Minimize2, RotateCcw, ShieldCheck, ThumbsDown, ThumbsUp } from 'lucide-react';
import clsx from 'clsx';
import { ask, sendFeedback, storedResult, type AskResult, type SemanticTrace, type SqlResult, EngineError } from '../lib/engine';
import { ResultChart } from './ResultChart';
import { pinId, type Tile } from '../lib/board';
import { downloadXlsx, questionToFileBase } from '../lib/xlsx';
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
      /** Cevabın hangi soruya ait olduğu — masaya iliştirilirken kartın başlığı bu. */
      question?: string;
      /** Motorun bu cevabı hesapladığı yürütme. Excel aktarımı tam sonucu bununla ister. */
      resultId?: string;
    };

const now = () => new Date().toLocaleTimeString('tr-TR', { hour: '2-digit', minute: '2-digit' });

/** Motorun bu cevabı hesaplarken çalıştırdığı sonuç. Yalnız gerçekten yürütülmüş bir cevapta vardır:
 *  reddedilen SQL yanıtta tanı amacıyla durur ve hiçbir şeyi çalıştırmaz. */
function resultOf(a: AskResult): SqlResult | undefined {
  if (a.type !== 'TEXT_TO_SQL' || !Array.isArray(a.records) || !Array.isArray(a.columns)) return undefined;
  return {
    id: String(a.resultId ?? a.id ?? ''),
    columns: a.columns as SqlResult['columns'],
    records: a.records as SqlResult['records'],
    totalRows: Number(a.totalRows ?? a.rowCount ?? (a.records as unknown[]).length),
    truncated: a.truncated as boolean | undefined,
    cached: a.cached as boolean | undefined,
    ageSec: a.ageSec as number | undefined,
    computedAt: a.computedAt as number | undefined,
    widget: a.widget as SqlResult['widget'],
    dataCoverage: a.dataCoverage as SqlResult['dataCoverage'],
  };
}

/** `net_ciro` → `Net ciro`. Kolonun makine adı ne başlıkta ne de cümlede öyle durmalı. */
export function columnLabel(name: string): string {
  const s = String(name).replace(/_/g, ' ').trim();
  return s ? s[0].toLocaleUpperCase('tr-TR') + s.slice(1) : String(name);
}

/** Satırlar zaten tablo olarak çiziliyorsa özetteki satır dökümü aynı veriyi ikinci kez yazar:
 *  yalnız baş cümle kalsın. Köprünün eski tek satırlık "… İlk satırlar: a=1, b=2" biçimi de
 *  kesilir — köprü güncellenmeden derlenmiş bir arayüz onu hâlâ görebilir. */
function headline(text: string): string {
  return text.split('\n')[0].replace(/\s*İlk\s+(satırlar|\d+)\s*:.*$/i, '').trim() || text;
}

export function CopilotPanel({
  engineOk, inputRef, onPin, pinned, module,
}: {
  module: ChatModule;
  engineOk: boolean | null;
  inputRef?: RefObject<HTMLInputElement>;
  /** Cevabı masaya iliştir. Verilmezse düğme çıkmaz — panel başka bir yerde de kullanılabilir. */
  onPin?: (tile: Tile) => void;
  pinned?: string[];
}) {
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
      // Tek yürütme: özet, tablo, grafik ve Excel hepsi motorun çalıştırdığı AYNI sonuçtan okur.
      // SQL'i ikinci kez /run_sql'e göndermek üç ayrı hataya yol açıyordu — dönem taşınmadığı için
      // yıllara bölünmüş tablolarda özetle tablo farklı sayı gösteriyor, sorgu iki kez çalışıyor, ve
      // motorun REDDETTİĞİ SQL (tanı için yanıtta duruyor) yine de çalıştırılıyordu.
      const result: SqlResult | undefined = resultOf(a);
      const text =
        a.summary?.trim() ||
        (result ? `${result.totalRows} satır döndü.` : (a.explanation?.trim() || 'Motor bu soru için SQL üretmedi.'));
      setMsgs((m) => [
        ...m.slice(0, -1),
        { role: 'assistant', text, sql: a.sql, result, at: now(), semantic: a.semantic, queryId: a.queryId, question: q, resultId: a.resultId },
      ]);
    } catch (e) {
      const msg = e instanceof EngineError ? `${e.message}${e.code ? ` (${e.code})` : ''}` : e instanceof Error ? e.message : String(e);
      setMsgs((m) => [...m.slice(0, -1), { role: 'assistant', text: 'Soru yanıtlanamadı.', error: msg, at: now() }]);
    } finally {
      setBusy(false);
    }
  }

  return (
    <aside className={clsx('card flex h-full min-h-[420px] w-full flex-col overflow-hidden sm:min-h-[560px] lg:sticky lg:top-20 lg:shrink-0', wide ? 'lg:w-[min(560px,42vw)]' : 'lg:w-[330px]')}>
      <div className="flex items-center gap-3 border-b border-line px-4 py-3">
        <div className="grid h-9 w-9 place-items-center rounded-xl bg-brand text-white">
          <Bot size={18} />
        </div>
        <div className="min-w-0 flex-1 leading-tight">
          <div className="flex items-center gap-2">
            <span className="font-display text-[15px] font-semibold">ZEKİ AI</span>
            <span className="rounded-md bg-page px-1.5 py-0.5 text-[10px] font-bold text-ink-muted">{module.title}</span>
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
            placeholder={module.placeholder}
            className="min-w-0 flex-1 bg-transparent text-[16px] outline-none placeholder:text-ink-faint"
            disabled={busy}
          />
          <button type="submit" disabled={busy || !input.trim()} className="grid h-11 w-11 shrink-0 place-items-center rounded-lg bg-brand text-white disabled:opacity-40">
            {busy ? <Loader2 size={15} className="animate-spin" /> : <ArrowUp size={15} />}
          </button>
        </div>
        <div className="mt-2 flex items-center justify-between text-[10px] text-ink-muted">
          <span className="inline-flex items-center gap-1"><Database size={11} /> Salt-okunur</span>
          <span className="hidden sm:inline">Enter ile gönder</span>
        </div>
      </form>
      <div className="mx-4 mt-3 rounded-xl bg-page px-3 py-2 text-[11px] text-ink-muted">
        {module.scope}
      </div>

      <div ref={listRef} className="scroll-thin flex-1 space-y-3 overflow-y-auto px-4 py-3">
        {msgs.length === 0 && (
          <div className="pt-2 text-[12px] text-ink-muted">
            Verilerinize Türkçe soru sorun. Örnek:
            <div className="mt-2 flex flex-wrap gap-1.5">
              {module.suggestions.map((s) => (
                <button key={s} onClick={() => send(s)} className="chip hover:border-brand hover:text-brand">
                  {s}
                </button>
              ))}
            </div>
          </div>
        )}
        {[...msgs].reverse().map((m, i) =>
          m.role === 'user' ? <UserBubble key={i} m={m} /> : m.pending ? <Thinking key={i} /> : <AssistantCard key={i} m={m} wide={wide} onPin={onPin} pinned={pinned} />,
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

function AssistantCard({
  m, wide, onPin, pinned,
}: {
  m: Extract<Msg, { role: 'assistant' }>;
  wide?: boolean;
  onPin?: (tile: Tile) => void;
  pinned?: string[];
}) {
  const [showSql, setShowSql] = useState(false);
  const [showTable, setShowTable] = useState(false);
  const cols = m.result?.columns ?? [];
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
        ZEKİ AI · {m.at}
      </div>
      <p className={clsx('mt-1.5 whitespace-pre-line text-[13px] leading-snug', m.error && 'text-brand-accent')}>
        {rows.length > 0 ? headline(m.text) : m.text}
      </p>
      {m.result && (
        <p className="mt-2 break-words text-xs leading-relaxed text-ink-muted">
          {m.result.truncated ? `Sonuç kesildi; en az ${m.result.totalRows} satır var. ` : `${m.result.totalRows} satır; ekranda ilk ${rows.length} satır. `}
          {m.result.computedAt ? `Hesaplanma: ${new Date(m.result.computedAt * 1000).toLocaleString('tr-TR')}. ` : ''}
          {m.result.cached ? `Önbellekten (${Math.round(m.result.ageSec ?? 0)} saniye önce).` : ''}
        </p>
      )}
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
      {(m.sql || rows.length > 0) && (
        <div className="mt-2">
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
            {m.sql && (
              <button onClick={() => setShowSql((v) => !v)} className="inline-flex items-center gap-1 text-[11px] font-semibold text-brand">
                {showSql ? <ChevronUp size={12} /> : <ChevronDown size={12} />} Üretilen SQL
              </button>
            )}
            {rows.length > 0 && m.result && <ExportButton m={m} result={m.result} />}
          </div>
          {showSql && m.sql && <pre className="mt-1 max-h-48 overflow-auto scroll-thin whitespace-pre-wrap break-words rounded-lg bg-ink p-2 text-[10px] text-white/90">{m.sql}</pre>}
        </div>
      )}
      {onPin && widget && m.sql && m.result && m.result.records.length > 0 && (
        <PinButton m={m} widget={widget} onPin={onPin} pinned={pinned} />
      )}
      {m.semantic && <SemanticTraceCard trace={m.semantic} />}
      {m.queryId && !m.error && <FeedbackRow queryId={m.queryId} />}
    </div>
  );
}

/** Bu cevabı masaya iliştir.
 *
 *  İliştirilen şey rakam değil sorgu: kart her açılışta yeniden hesaplar. Aynı soru iki kez
 *  eklenmesin diye kimlik sorunun ve SQL'in kendisinden türetiliyor. */
function PinButton({
  m, widget, onPin, pinned,
}: {
  m: Extract<Msg, { role: 'assistant' }>;
  widget: NonNullable<SqlResult['widget']>;
  onPin: (tile: Tile) => void;
  pinned?: string[];
}) {
  const id = pinId(m.question ?? widget.title, m.sql ?? '');
  const already = pinned?.includes(id) ?? false;
  const [done, setDone] = useState(false);
  return (
    <button
      type="button"
      disabled={already || done}
      onClick={() => {
        onPin({
          id, kind: 'pinned', span: 2,
          title: widget.title || m.question || 'Sorgu',
          question: m.question ?? widget.title ?? '',
          sql: m.sql ?? '',
          chart: widget.type, xKey: widget.x_key, yKey: widget.y_key,
          labelKey: widget.label_key, valueKey: widget.value_key, format: widget.format,
          pinnedAt: Date.now(),
        });
        setDone(true);
      }}
      className={clsx('mt-2 inline-flex items-center gap-1 rounded-lg border px-2 py-1 text-[11px] font-medium transition',
        already || done ? 'border-line bg-page text-ink-faint' : 'border-brand/30 bg-brand-soft text-brand-deep hover:border-brand/60')}
    >
      <LayoutDashboard size={12} /> {already || done ? 'masada' : 'masaya ekle'}
    </button>
  );
}

/** Sonucu Excel'e aktar.
 *
 *  Ekranda ilk 8-20 satır görünür; dosyaya sorgunun tamamı gitsin diye SQL, aktarma anında yüksek
 *  bir sınırla yeniden koşturulur. Köprü kendi üst sınırında keserse (`truncated`) bu sessizce
 *  geçilmez: hem düğmenin altında hem dosyanın künye sayfasında yazar. Dosya adı sorudan üretilir. */
function ExportButton({ m, result }: { m: Extract<Msg, { role: 'assistant' }>; result: SqlResult }) {
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<{ file: string; rows: number; partial: boolean } | null>(null);
  const [failed, setFailed] = useState<string | null>(null);

  async function run() {
    if (busy) return;
    setBusy(true);
    setFailed(null);
    try {
      // Aynı yürütmenin TAM sonucu. Ekrandaki sayfa "tam sonuç" diye indirilmemeli; SQL'i yeniden
      // koşturmak da başka bir yürütme demektir — veri değişmiş olabilir, dönem taşınmaz.
      let full = result;
      let stale: string | null = null;
      if (m.resultId) {
        try {
          full = await storedResult(m.resultId);
        } catch (e) {
          const gone = e instanceof EngineError && e.code === 'RESULT_GONE';
          stale = gone
            ? 'Bu sonucun saklama süresi dolmuş; dosyada ekranda görünen satırlar var. Tamamı için aynı soruyu tekrar sorun.'
            : 'Tam sonuç alınamadı; dosyada ekranda görünen satırlar var.';
          full = result;
        }
      }
      const file = await downloadXlsx({
        fileBase: questionToFileBase(m.question || 'sorgu sonucu'),
        columns: full.columns.map((c) => ({ key: c.name, label: columnLabel(c.name) })),
        rows: full.records,
        question: m.question,
        sql: m.sql,
        meta: [
          ...(full.dataCoverage || []).map((c) => ({
            label: `Veri kapsamı (${c.period.text || c.period.start})`,
            value: `${c.observedStart} – ${c.observedEnd}; yükleme bütünlüğü doğrulanmadı. Sonuç yalnız mevcut kayıtlara aittir.`,
          })),
          ...(full.truncated
            ? [{ label: 'Uyarı', value: `Sonuç sunucu satır sınırında kesildi: ${full.records.length} satır aktarıldı, sorgu bunun ötesinde devam ediyor.` }]
            : []),
          ...(stale ? [{ label: 'Uyarı', value: stale }] : []),
          ...(full.records.length < (full.totalRows || 0)
            ? [{ label: 'Uyarı', value: `Bu dosyada ${full.records.length} satır var; yürütme ${full.totalRows} satır döndürdü.` }]
            : []),
        ],
      });
      setNote({ file, rows: full.records.length, partial: Boolean(full.truncated) || Boolean(stale) });
    } catch (e) {
      setFailed(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <button
        type="button"
        onClick={run}
        disabled={busy}
        className="inline-flex items-center gap-1 text-[11px] font-semibold text-brand disabled:opacity-50"
        title="Sonucu biçimlendirilmiş .xlsx olarak indir"
      >
        {busy ? <Loader2 size={12} className="animate-spin" /> : note ? <Check size={12} className="text-ok" /> : <FileSpreadsheet size={12} />}
        {busy ? 'Hazırlanıyor…' : 'Excel’e aktar'}
      </button>
      {note && (
        <div className="basis-full text-[10px] text-ink-muted">
          <span className="font-mono">{note.file}</span> indirildi · {note.rows} satır
          {note.partial && <span className="text-brand-accent"> · sunucu sınırında kesildi, tamamı değil</span>}
        </div>
      )}
      {failed && <div className="basis-full text-[10px] text-brand-accent">Aktarma başarısız: {failed}</div>}
    </>
  );
}

/** Sonuç tablosu.
 *
 *  Okunurluk kararları: kolon adı makine adıyla değil ("Net ciro"), sayı kolonu sağa dayalı ve
 *  sabit genişlikli rakamlarla (basamaklar alt alta gelsin diye), uzun metin kırpılır ama tam hali
 *  hücrenin üstüne gelince görünür, satırlar zebra — dar panelde göz satırı kaybetmesin. */
function ResultTable({
  cols,
  rows,
  totalRows,
}: {
  cols: { name: string; type: string }[];
  rows: Record<string, unknown>[];
  totalRows: number;
}) {
  // Kolonun sayısal olup olmadığı tipe değil değere bakılarak belirlenir: sürücü tipi her zaman gelmiyor.
  const numeric = cols.map((c) => {
    const seen = rows.map((r) => r[c.name]).filter((v) => v != null && v !== '');
    return seen.length > 0 && seen.every((v) => typeof v === 'number');
  });
  return (
    <div className="mt-2 overflow-hidden rounded-xl border border-line">
      <div className="overflow-x-auto scroll-thin">
        <table className="w-full border-collapse text-[11px]">
          <thead>
            <tr className="bg-page">
              {cols.map((c, i) => (
                <th
                  key={c.name}
                  className={clsx(
                    'whitespace-nowrap border-b border-line px-2.5 py-1.5 text-[10px] font-semibold uppercase tracking-wide text-ink-muted',
                    numeric[i] ? 'text-right' : 'text-left',
                  )}
                >
                  {columnLabel(c.name)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((r, i) => (
              <tr key={i} className={clsx('border-b border-line/50 last:border-0', i % 2 === 1 && 'bg-page/45')}>
                {cols.map((c, ci) => {
                  const v = r[c.name];
                  const text = fmtCell(v);
                  return (
                    <td
                      key={c.name}
                      title={text}
                      className={clsx(
                        'px-2.5 py-1.5 align-top',
                        numeric[ci]
                          ? 'whitespace-nowrap text-right font-medium tabular-nums text-ink'
                          : 'max-w-[190px] truncate text-ink-muted',
                        v == null || v === '' ? 'text-ink-faint' : null,
                      )}
                    >
                      {text || '—'}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="flex items-center justify-between gap-2 border-t border-line bg-page px-2.5 py-1 text-[10px] text-ink-muted">
        <span>{totalRows > rows.length ? `İlk ${rows.length} / ${totalRows} satır` : `${totalRows} satır`}</span>
        <span className="text-ink-faint">tamamı Excel aktarımında</span>
      </div>
    </div>
  );
}

function fmtCell(v: unknown): string {
  if (v == null) return '';
  if (typeof v === 'boolean') return v ? 'Evet' : 'Hayır';
  if (typeof v === 'number') return new Intl.NumberFormat('tr-TR', { maximumFractionDigits: 2 }).format(v);
  return String(v);
}
