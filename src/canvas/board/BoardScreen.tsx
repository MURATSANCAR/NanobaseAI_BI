import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useQueries, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  Box,
  Check,
  ChevronDown,
  Clock,
  Code2,
  Copy,
  Download,
  FileSpreadsheet,
  FileText,
  GripVertical,
  Loader2,
  Pencil,
  Plus,
  RefreshCw,
  RotateCw,
  Send,
  Timer,
  Trash2,
  X,
} from 'lucide-react';
import {
  ENGINE_BASE,
  ENGINE_ENABLED,
  EngineAuthError,
  ask as askEngine,
  boardApi,
  type BoardCardResult,
  type BoardRefresh,
  type SqlResult,
} from '../engine';
import { stamp } from '../format';
import Chart, { CHART_LABEL, allowedCharts, numericCols, suggestChart, type Col, type Row } from './Chart';
import { download, fileName, toCsv } from './export';
import {
  fromDto,
  loadBoard,
  newId,
  nextSlot,
  saveBoard,
  snap,
  topZ,
  type BoardCard,
  type ChartKind,
  loadResults,
  saveResult,
  dropResult,
  type CardResult,
} from './store';
import Shell from '../stitch/Shell';
import { railFor } from '../stitch/screens';

/** Giriş yapan kişi; pano ona ait. */
function useUser(): string {
  const q = useQuery({
    queryKey: ['timas-session'],
    queryFn: async () => {
      const res = await fetch(`${ENGINE_BASE}/auth/session`, { credentials: 'include' });
      if (!res.ok) throw new EngineAuthError();
      return (await res.json()) as { username: string };
    },
    enabled: ENGINE_ENABLED,
    retry: false,
    staleTime: 5 * 60_000,
  });
  return q.data?.username ?? '';
}

const INTERACTIVE = 'a, button, input, select, textarea, [data-nodrag]';

/** SQL paneli açıkken kart bu kadar uzar; grafik küçülmez, panel altına eklenir. */
const SQL_EXTRA = 160;

const REFRESH_LABEL: Record<BoardRefresh, string> = { manual: 'Elle', hourly: 'Saatte bir', daily: 'Her gün' };

/** KPI kartı için karşılaştırma ekleri; soru bu ekle yeniden sorulur. */
const COMPARE = [
  { key: 'yil', label: 'geçen yıla göre' },
  { key: 'ay', label: 'geçen aya göre' },
] as const;

/** Dar ekran (<768 px). Panoda kartlar orada alt alta dizilir. */
function useNarrow(): boolean {
  const query = '(max-width: 767px)';
  const [narrow, setNarrow] = useState(() => typeof window !== 'undefined' && window.matchMedia(query).matches);
  useEffect(() => {
    const mq = window.matchMedia(query);
    const on = () => setNarrow(mq.matches);
    on();
    mq.addEventListener('change', on);
    return () => mq.removeEventListener('change', on);
  }, []);
  return narrow;
}

/** Panoya SQL kopyalama düğmesi; iki saniye "Kopyalandı" der. */
function CopySql({ sql }: { sql: string }) {
  const [done, setDone] = useState(false);
  useEffect(() => {
    if (!done) return;
    const t = window.setTimeout(() => setDone(false), 2000);
    return () => window.clearTimeout(t);
  }, [done]);
  return (
    <button
      type="button"
      onClick={() => {
        void navigator.clipboard?.writeText(sql).then(() => setDone(true));
      }}
      className="pano-press flex h-8 items-center gap-1 rounded-lg px-2 text-[11px] font-bold text-canvas-muted transition-colors hover:bg-slate-100 hover:text-canvas-ink"
      title="SQL'i kopyala"
    >
      {done ? <Check className="h-3.5 w-3.5 text-canvas-mint" /> : <Copy className="h-3.5 w-3.5" />}
      {done ? 'Kopyalandı' : 'Kopyala'}
    </button>
  );
}

/** Kartın altındaki SQL paneli: kendi içinde kayar, sayfayı taşırmaz. */
function SqlPanel({ sql, className = '' }: { sql: string; className?: string }) {
  return (
    <div data-nodrag className={['pano-sql flex min-h-0 flex-col', className].join(' ')}>
      <div className="flex items-center justify-between gap-2 pb-1">
        <span className="flex items-center gap-1 text-[11px] font-extrabold uppercase tracking-wide text-canvas-muted">
          <Code2 className="h-3.5 w-3.5" />
          Çalışan SQL
        </span>
        <CopySql sql={sql} />
      </div>
      <pre className="min-h-0 flex-1 overflow-auto rounded-xl bg-slate-950 p-3 font-mono text-[11px] leading-relaxed text-slate-100 selection:bg-canvas-violet/40">
        {sql.trim()}
      </pre>
    </div>
  );
}

/** Kart araç şeridindeki seçici: tarayıcının kaba select kutusu yerine şeritle aynı boyda, oklu. */
function ToolSelect({
  value,
  onChange,
  title,
  disabled,
  icon,
  children,
}: {
  value: string;
  onChange: (v: string) => void;
  title?: string;
  disabled?: boolean;
  icon?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <label
      title={title}
      className="relative flex h-7 items-center gap-1 rounded-md border border-slate-200 bg-white pl-2 pr-6 text-[11px] font-semibold text-canvas-ink transition-colors hover:border-slate-300 has-[:disabled]:opacity-60"
    >
      {icon}
      <select
        value={value}
        disabled={disabled}
        onChange={(e) => onChange(e.target.value)}
        className="cursor-pointer appearance-none bg-transparent outline-none"
      >
        {children}
      </select>
      <ChevronDown className="pointer-events-none absolute right-1.5 h-3 w-3 text-canvas-muted" />
    </label>
  );
}

/** Başlık ve not: kaleme basınca yerinde düzenlenir, Enter/Kaydet yazar. */
function EditableHead({ card, onChange }: { card: BoardCard; onChange: (p: Partial<BoardCard>) => void }) {
  const [editing, setEditing] = useState(false);
  const [title, setTitle] = useState(card.title);
  const [note, setNote] = useState(card.note ?? '');
  useEffect(() => {
    if (!editing) {
      setTitle(card.title);
      setNote(card.note ?? '');
    }
  }, [card.title, card.note, editing]);
  const commit = () => {
    const t = title.trim() || card.title;
    const n = note.trim();
    if (t !== card.title || n !== (card.note ?? '')) onChange({ title: t, note: n || undefined });
    setEditing(false);
  };
  if (editing) {
    return (
      <div data-nodrag className="flex flex-col gap-1">
        <input
          autoFocus
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter') commit();
            if (e.key === 'Escape') setEditing(false);
          }}
          placeholder="Kart başlığı"
          className="w-full rounded-lg border border-canvas-violet/40 bg-white px-2 py-1 text-[12.5px] font-extrabold outline-none ring-2 ring-canvas-violet/15"
        />
        <textarea
          value={note}
          onChange={(e) => setNote(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Escape') setEditing(false);
          }}
          rows={2}
          placeholder="İş notu (isteğe bağlı): ne anlatıyor, kim bakmalı…"
          className="w-full resize-none rounded-lg border border-slate-200 bg-white px-2 py-1 text-[11.5px] font-medium outline-none focus:border-canvas-violet/40"
        />
        <div className="flex gap-1">
          <button type="button" onClick={commit} className="pano-press h-7 rounded-lg bg-canvas-violet px-2.5 text-[11px] font-bold text-white">
            Kaydet
          </button>
          <button type="button" onClick={() => setEditing(false)} className="pano-press h-7 rounded-lg px-2 text-[11px] font-bold text-canvas-muted hover:bg-slate-100">
            Vazgeç
          </button>
        </div>
      </div>
    );
  }
  return (
    <div className="flex min-w-0 items-start gap-1">
      <div className="min-w-0 flex-1">
        <div
          className="truncate text-[14px] font-bold leading-7 text-canvas-ink"
          title={card.question && card.question !== card.title ? `Soru: ${card.question}` : card.title}
        >
          {card.title}
        </div>
        {card.note && <div className="line-clamp-2 text-[11px] font-medium leading-snug text-canvas-muted">{card.note}</div>}
      </div>
      <button
        type="button"
        onClick={() => setEditing(true)}
        title="Başlığı ve notu düzenle"
        className="pano-press pano-noprint flex h-7 w-7 shrink-0 items-center justify-center rounded-lg text-canvas-muted transition-colors hover:bg-slate-100 hover:text-canvas-ink md:opacity-0 md:group-hover/card:opacity-100 md:focus-visible:opacity-100"
      >
        <Pencil className="h-3 w-3" />
      </button>
    </div>
  );
}

function CardFrame({
  card,
  onChange,
  onFront,
  onRemove,
  children,
  head,
  toolbar,
  actions,
  foot,
  stacked = false,
}: {
  card: BoardCard;
  onChange: (patch: Partial<BoardCard>) => void;
  /** Tutulan kart öne gelir. */
  onFront: () => void;
  onRemove: () => void;
  children: React.ReactNode;
  head: React.ReactNode;
  /** Başlığın altında, kartın tam genişliğinde: grafik tipi, zamanlama, karşılaştırma. */
  toolbar?: React.ReactNode;
  /** Başlık satırının sağı: yenile, sil. */
  actions?: React.ReactNode;
  foot: React.ReactNode;
  /** Telefonda kart konumsuz, tam genişlikte; sürükleme parmakla kaydırmayı kilitlemesin. */
  stacked?: boolean;
}) {
  const [live, setLive] = useState<{ dx: number; dy: number; w: number; h: number } | null>(null);
  const [mode, setMode] = useState<'move' | 'size' | null>(null);
  const start = useRef({ x: 0, y: 0, cx: 0, cy: 0, w: 0, h: 0 });

  const down = (e: React.PointerEvent, m: 'move' | 'size') => {
    if (mode) return; // ikinci parmak/tuş sürüklemeyi devralmasın
    if (m === 'move' && (e.target as HTMLElement).closest(INTERACTIVE)) return;
    if (e.button !== 0) return;
    e.stopPropagation();
    setMode(m);
    start.current = { x: e.clientX, y: e.clientY, cx: card.x, cy: card.y, w: card.w, h: card.h };
    (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
    if (m === 'move') onFront();
  };
  const move = (e: React.PointerEvent) => {
    if (!mode) return;
    const dx = e.clientX - start.current.x;
    const dy = e.clientY - start.current.y;
    if (mode === 'move') {
      // Izgaraya oturarak taşınır; bırakınca sıçramaz.
      const nx = Math.max(0, snap(start.current.cx + dx));
      const ny = Math.max(0, snap(start.current.cy + dy));
      setLive({ dx: nx - card.x, dy: ny - card.y, w: card.w, h: card.h });
    } else {
      setLive({
        dx: 0,
        dy: 0,
        w: Math.max(280, snap(start.current.w + dx)),
        h: Math.max(220, snap(start.current.h + dy)),
      });
    }
  };
  const up = () => {
    if (live) {
      onChange(mode === 'move' ? { x: card.x + live.dx, y: card.y + live.dy } : { w: live.w, h: live.h });
    }
    setLive(null);
    setMode(null);
  };

  const w = live?.w ?? card.w;
  const h = (live?.h ?? card.h) + (card.sqlOpen ? SQL_EXTRA : 0);
  const shift = live && mode === 'move' ? `translate(${live.dx}px, ${live.dy}px)` : undefined;

  return (
    <div
      className={stacked ? 'pano-frame group/card relative w-full' : 'pano-frame group/card absolute'}
      data-drag={mode ?? undefined}
      // Telefonda kart içeriği kadar uzar; grafik alanı sabit (aşağıda), başlık/not/kontroller onu ezmez.
      style={stacked ? undefined : { left: card.x, top: card.y, width: w, height: h, transform: shift, zIndex: mode ? 999 : (card.z ?? 20) }}
      onPointerDown={stacked ? undefined : (e) => down(e, 'move')}
      onPointerMove={stacked ? undefined : move}
      onPointerUp={stacked ? undefined : up}
      onPointerCancel={stacked ? undefined : up}
    >
      <div className="glass-card pano-card flex h-full flex-col rounded-[22px] p-3 shadow-canvas-card sm:p-4">
        <div className={['border-b border-slate-100 pb-2', stacked ? '' : 'pano-handle cursor-grab'].join(' ')}>
          <div className="flex items-start gap-1.5">
            {!stacked && (
              <span
                className="pano-noprint -ml-1 flex h-7 shrink-0 items-center text-slate-300 transition-colors group-hover/card:text-slate-400"
                title="Sürükleyip taşı"
                aria-hidden
              >
                <GripVertical className="h-4 w-4" />
              </span>
            )}
            <div className="min-w-0 flex-1">{head}</div>
            <div className="pano-noprint flex shrink-0 items-center gap-0.5">
              {actions}
              <button
                type="button"
                onClick={onRemove}
                title="Karttan çıkar"
                className="pano-press flex h-7 w-7 items-center justify-center rounded-md text-canvas-muted transition-colors hover:bg-red-50 hover:text-red-600 md:opacity-0 md:group-hover/card:opacity-100 md:focus-visible:opacity-100"
              >
                <Trash2 className="h-3.5 w-3.5" />
              </button>
            </div>
          </div>
          {toolbar && <div className="pano-noprint mt-1.5 flex flex-wrap items-center gap-1.5">{toolbar}</div>}
        </div>
        <div className="flex min-h-0 flex-1 flex-col pt-2">{children}</div>
        <div className="mt-2 flex flex-wrap items-center justify-between gap-x-3 gap-y-1 border-t border-slate-100 pt-1.5">{foot}</div>
      </div>
      {!stacked && (
        <span
          onPointerDown={(e) => down(e, 'size')}
          onPointerMove={move}
          onPointerUp={up}
          onPointerCancel={up}
          title="Boyutlandır"
          className="pano-noprint absolute -bottom-1 -right-1 h-5 w-5 cursor-nwse-resize rounded-full border-2 border-white bg-slate-300/90 opacity-0 shadow transition-opacity hover:bg-canvas-violet group-hover/card:opacity-100"
        />
      )}
    </div>
  );
}

type Pending = { title: string; sql: string; cols: Col[]; rows: Row[]; chart: ChartKind; at: number };

/**
 * Kişiye özel pano. Soru sorulur, gelen sonuç grafiğe çevrilir, "Panoya ekle"
 * denince kart olarak sabitlenir. Kartlar taşınır, boyutlandırılır, tipi
 * değiştirilir; düzen ve son sonuçlar sunucuda kişinin adına durur.
 *
 * Kart verisi donmuş değildir: saklanan şey SQL'dir; sunucu elle, 5 dk bayatlıkta
 * ya da zamanlayıcıyla yeniden koşar. Açılışta sorgu yok, son sonuç anında çizilir.
 */
export default function BoardScreen() {
  const user = useUser();
  const [cards, setCards] = useState<BoardCard[]>([]);
  const [prompt, setPrompt] = useState('');
  const [pending, setPending] = useState<Pending | null>(null);
  const [pendingSql, setPendingSql] = useState(false);
  const [asking, setAsking] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [saveState, setSaveState] = useState<'idle' | 'saving' | 'failed'>('idle');
  const [comparing, setComparing] = useState<string | null>(null);
  /** Excel üretilirken: 'all' ya da kart kimliği. */
  const [exporting, setExporting] = useState<string | null>(null);
  /** PDF: kartlar yazdırma için alt alta, animasyonsuz dizilir; pencere kapanınca eski düzen döner. */
  const [printing, setPrinting] = useState(false);
  const qc = useQueryClient();

  // Açılış: önce tarayıcıdaki kopya (anında), sonra sunucudaki doğrusu.
  const serverResults = useRef<Record<string, BoardCardResult>>({});
  const board = useQuery({
    queryKey: ['pano-board', user],
    queryFn: () => boardApi.load(),
    enabled: ENGINE_ENABLED && Boolean(user),
    retry: false,
    staleTime: Infinity,
  });

  useEffect(() => {
    if (!user) return;
    setCards(loadBoard(user));
  }, [user]);

  const migrated = useRef(false);
  useEffect(() => {
    if (!board.data || !user) return;
    const local = loadBoard(user);
    if (!board.data.cards.length && local.length && !migrated.current) {
      // Eski tarayıcı panosu bir kez sunucuya taşınır.
      migrated.current = true;
      void boardApi.save(local).then((res) => {
        setCards(res.cards.map(fromDto));
      });
      return;
    }
    const next = board.data.cards.map(fromDto);
    for (const d of board.data.cards) if (d.result) serverResults.current[d.id] = d.result;
    setCards(next);
    // Sunucu boşsa tarayıcıdaki kopya silinmez; tek yön doğrusu sunucudan gelendir.
    if (next.length) saveBoard(user, next);
  }, [board.data, user]);

  const saveTimer = useRef<number | null>(null);
  const pushToServer = useCallback((next: BoardCard[]) => {
    setSaveState('saving');
    return boardApi
      .save(next)
      .then(() => setSaveState('idle'))
      .catch(() => setSaveState('failed'));
  }, []);

  /** Yerel + sunucu; sunucu yazımı 500 ms toplanır (sürüklerken her piksel gitmesin). */
  const persist = useCallback(
    (next: BoardCard[]) => {
      setCards(next);
      saveBoard(user, next);
      if (!ENGINE_ENABLED || !user) return;
      if (saveTimer.current) window.clearTimeout(saveTimer.current);
      saveTimer.current = window.setTimeout(() => void pushToServer(next), 500);
    },
    [user, pushToServer],
  );

  // Kart önce son sonucuyla anında çizilir; beş dakikadan eskiyse sunucu
  // SQL'i yeniden koşar (sonuç orada da güncellenir) ve kart kendini tazeler.
  const cached = useMemo(() => loadResults(user), [user]);
  const results = useQueries({
    queries: cards.map((c) => {
      const hit = serverResults.current[c.id] ?? cached[c.id];
      return {
        queryKey: ['pano', c.id, c.sql],
        queryFn: async () => {
          const r = await boardApi.run(c.id);
          saveResult(user, c.id, r as CardResult);
          return r as SqlResult<Row>;
        },
        initialData: hit ? (hit as unknown as SqlResult<Row>) : undefined,
        initialDataUpdatedAt: hit?.at,
        enabled: ENGINE_ENABLED && Boolean(c.sql) && Boolean(board.data),
        staleTime: 5 * 60_000,
        retry: false,
      };
    }),
  });

  const ask = async () => {
    const q = prompt.trim();
    if (!q || !ENGINE_ENABLED) return;
    setAsking(true);
    setErr(null);
    setPending(null);
    setPendingSql(false);
    try {
      const a = await askEngine(q);
      const cols = (a.columns ?? []) as Col[];
      const rows = (a.records ?? []) as Row[];
      if (!a.sql || !rows.length) {
        setErr(a.summary || a.explanation || 'Zeki AI bu soruya tablo döndürmedi.');
      } else {
        setPending({ title: q, sql: a.sql, cols, rows, chart: suggestChart(cols, rows), at: Date.now() });
      }
    } catch (e) {
      setErr(e instanceof EngineAuthError ? 'Oturum gerekli.' : 'Zeki AI yanıt vermedi.');
    } finally {
      setAsking(false);
    }
  };

  const addPending = async () => {
    if (!pending) return;
    const slot = nextSlot(cards);
    const card: BoardCard = {
      id: newId(),
      title: pending.title,
      question: pending.title,
      sql: pending.sql,
      chart: pending.chart,
      depth: false,
      z: topZ(cards),
      refresh: 'manual',
      createdAt: new Date().toISOString(),
      ...slot,
    };
    const next = [...cards, card];
    setCards(next);
    saveBoard(user, next);
    // Önizleme ilk 50 satırdır; kart onunla hemen çizilir ama bayat sayılır ve tam sonuç hemen istenir.
    const seed = { columns: pending.cols, records: pending.rows } as SqlResult<Row>;
    qc.setQueryData(['pano', card.id, card.sql], seed, { updatedAt: pending.at });
    saveResult(user, card.id, { ...(seed as unknown as CardResult), at: pending.at });
    setPending(null);
    setPendingSql(false);
    setPrompt('');
    if (saveTimer.current) window.clearTimeout(saveTimer.current);
    await pushToServer(next); // sunucu kartı bilmeden koşturamaz
    void qc.invalidateQueries({ queryKey: ['pano', card.id, card.sql] });
  };

  const patch = (id: string, p: Partial<BoardCard>) => persist(cards.map((c) => (c.id === id ? { ...c, ...p } : c)));
  const front = (id: string) => {
    const c = cards.find((k) => k.id === id);
    if (!c) return;
    const z = topZ(cards);
    if ((c.z ?? 20) < z - 1) patch(id, { z });
  };
  const remove = (id: string) => {
    dropResult(user, id);
    delete serverResults.current[id];
    persist(cards.filter((c) => c.id !== id));
  };

  /** KPI kartını karşılaştırmalı hâle çevirir: soru "geçen yıla göre" ekiyle yeniden sorulur. */
  const compare = async (card: BoardCard, suffix: string) => {
    if (!ENGINE_ENABLED) return;
    setComparing(card.id);
    setErr(null);
    try {
      const q = `${card.question || card.title} ${suffix}`;
      const a = await askEngine(q);
      const cols = (a.columns ?? []) as Col[];
      const rows = (a.records ?? []) as Row[];
      const sql = a.sql;
      if (!sql || rows.length !== 1 || numericCols(cols, rows).length < 2) {
        setErr(a.summary || 'Zeki AI bu karşılaştırmayı tek satırda iki sayı olarak veremedi.');
        return;
      }
      const next = cards.map((c) => (c.id === card.id ? { ...c, sql, question: q, chart: 'kpi' as ChartKind } : c));
      setCards(next);
      saveBoard(user, next);
      const seed = { columns: cols, records: rows } as SqlResult<Row>;
      qc.setQueryData(['pano', card.id, sql], seed, { updatedAt: Date.now() });
      saveResult(user, card.id, { ...(seed as unknown as CardResult), at: Date.now() });
      if (saveTimer.current) window.clearTimeout(saveTimer.current);
      await pushToServer(next);
      void qc.invalidateQueries({ queryKey: ['pano', card.id, sql] });
    } catch (e) {
      setErr(e instanceof EngineAuthError ? 'Oturum gerekli.' : 'Zeki AI yanıt vermedi.');
    } finally {
      setComparing(null);
    }
  };

  /** Excel sunucuda üretilir: SQL tam koşar, her kart bir sayfa, grafik Excel'in kendi grafiği. */
  const exportExcel = async (ids: string[], key: string) => {
    if (!ENGINE_ENABLED || exporting) return;
    setExporting(key);
    setErr(null);
    try {
      if (saveTimer.current) {
        // Bekleyen düzen kaydı önce gitsin; sunucu kartı bilmeden aktaramaz.
        window.clearTimeout(saveTimer.current);
        saveTimer.current = null;
        await pushToServer(cards);
      }
      const { blob, name } = await boardApi.exportXlsx(ids);
      download(name, blob);
    } catch (e) {
      setErr(e instanceof EngineAuthError ? 'Oturum gerekli.' : e instanceof Error ? e.message : 'Excel üretilemedi.');
    } finally {
      setExporting(null);
    }
  };

  useEffect(() => {
    if (!printing) return;
    const done = () => setPrinting(false);
    window.addEventListener('afterprint', done);
    // Alt alta düzen ve grafikler yeni genişliğe otursun, sonra yazdırma penceresi açılsın.
    let raf = 0;
    const t = window.setTimeout(() => {
      raf = window.requestAnimationFrame(() => window.print());
    }, 450);
    return () => {
      window.clearTimeout(t);
      window.cancelAnimationFrame(raf);
      window.removeEventListener('afterprint', done);
    };
  }, [printing]);

  const refreshAll = () => {
    for (const r of results) void r.refetch();
  };
  const anyFetching = results.some((r) => r.isFetching);
  const lastRun = results.reduce((m, r) => Math.max(m, r.dataUpdatedAt || 0), 0);

  const height = useMemo(
    () => Math.max(720, ...cards.map((c) => c.y + c.h + (c.sqlOpen ? SQL_EXTRA : 0) + 40)),
    [cards],
  );

  const narrowScreen = useNarrow();
  const narrow = narrowScreen || printing;
  const pendingAllowed = pending ? allowedCharts(pending.cols, pending.rows) : [];

  return (
    <Shell
      head={{
        tenant: 'Timaş Yayınları',
        section: 'Yapay Zeka Raporları',
        crumb: 'Panom',
        source: user || 'oturum yok',
        presence: `${cards.length} kart`,
        zoom: '%100',
      }}
      rail={railFor('/panolar')}
    >
      {/* Araç şeridi: tümünü yenile, PDF, kayıt durumu */}
      {cards.length > 0 && (
        <div className="pano-noprint absolute left-14 right-2 top-14 z-30 flex justify-end sm:left-[92px] sm:right-6 sm:top-[76px]">
          <div className="glass-panel flex items-center gap-1 rounded-full px-1.5 py-1 shadow-glass-float">
            <button
              type="button"
              onClick={refreshAll}
              disabled={anyFetching}
              title="Bütün kartları şimdi yeniden sorgula"
              className="pano-press flex h-8 items-center gap-1.5 rounded-full px-2.5 text-[11px] font-bold text-canvas-ink transition-colors hover:bg-white disabled:opacity-60"
            >
              <RefreshCw className={['h-3.5 w-3.5', anyFetching ? 'animate-spin' : ''].join(' ')} />
              <span className="hidden sm:inline">Tümünü yenile</span>
            </button>
            <button
              type="button"
              onClick={() => void exportExcel([], 'all')}
              disabled={exporting != null}
              title="Bütün kartlar tek Excel dosyasında: her kart bir sayfa, tam veri ve grafik"
              className="pano-press flex h-8 items-center gap-1.5 rounded-full px-2.5 text-[11px] font-bold text-canvas-ink transition-colors hover:bg-white disabled:opacity-60"
            >
              {exporting === 'all' ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <FileSpreadsheet className="h-3.5 w-3.5 text-emerald-700" />}
              Excel
            </button>
            <button
              type="button"
              onClick={() => setPrinting(true)}
              disabled={printing}
              title="Panoyu PDF olarak kaydet (yazdırma penceresi)"
              className="pano-press flex h-8 items-center gap-1.5 rounded-full px-2.5 text-[11px] font-bold text-canvas-ink transition-colors hover:bg-white disabled:opacity-60"
            >
              <FileText className="h-3.5 w-3.5 text-red-600" />
              PDF
            </button>
            <span className="hidden items-center gap-1 border-l border-slate-200/80 pl-2 pr-1 text-[11px] font-semibold text-canvas-muted sm:flex">
              {saveState === 'saving' ? (
                <>
                  <Loader2 className="h-3 w-3 animate-spin" /> Kaydediliyor
                </>
              ) : saveState === 'failed' ? (
                <span className="text-red-600">Kaydedilemedi</span>
              ) : board.isError ? (
                <span className="text-amber-600">Sunucuya ulaşılamadı</span>
              ) : (
                <>
                  <Clock className="h-3 w-3" /> Son sorgu {stamp(lastRun)}
                </>
              )}
            </span>
          </div>
        </div>
      )}

      {/* Yazdırma başlığı: yalnız kâğıtta */}
      <div className="pano-print-head mb-3 hidden text-[12px] text-canvas-muted">
        <span className="text-base font-extrabold text-canvas-ink">Panom · {user}</span> · {stamp(Date.now())} · {cards.length} kart
      </div>

      {/* Kartlar */}
      <main className="pano-print-main pano-scroll absolute bottom-[152px] left-14 right-2 top-[104px] sm:bottom-[118px] sm:left-[92px] sm:right-6 sm:top-[124px] overflow-auto">
        <div
          // Yazdırırken genişlik A4'ün yazı alanıdır (~700 px): grafikler kâğıttaki boyuta göre çizilir, sonradan esnemez.
          className={
            printing
              ? 'pano-print-stack mx-auto flex w-[700px] flex-col gap-3 pb-3'
              : narrow
                ? 'mx-auto flex w-full flex-col gap-3 pb-3'
                : 'relative mx-auto w-full max-w-[1760px]'
          }
          style={narrow ? undefined : { height }}
        >
          {!cards.length && !pending && (
            <div className="flex h-[420px] flex-col items-center justify-center text-center">
              <div className="glass-card rounded-3xl px-8 py-7 shadow-canvas-card">
                <Box className="mx-auto h-7 w-7 text-canvas-violet" />
                <h2 className="mt-3 text-base font-extrabold">Panonuz boş</h2>
                <p className="mt-1.5 max-w-[340px] text-[12.5px] leading-snug text-canvas-muted">
                  Aşağıya bir soru yazın. Gelen sonucu beğenirseniz “Panoya ekle” deyin, kart burada sabit kalsın.
                  Kartları başlığından tutup sürükleyebilir, köşesinden büyütebilirsiniz. Pano hesabınıza bağlıdır; başka
                  bilgisayarda da aynı görünür.
                </p>
              </div>
            </div>
          )}

          {cards.map((c, i) => {
            const r = results[i];
            const cols = (r?.data?.columns ?? []) as Col[];
            const rows = (r?.data?.records ?? []) as Row[];
            // Veri gelmeden izinli liste yalnız "Tablo" olur; kayıtlı seçim yine görünsün.
            const allowed = allowedCharts(cols, rows);
            const options = allowed.includes(c.chart) ? allowed : [c.chart, ...allowed];
            const sqlOpen = Boolean(c.sqlOpen);
            const numCount = numericCols(cols, rows).length;
            const isKpi = c.chart === 'kpi' || (rows.length === 1 && numCount >= 1);
            const compared = rows.length === 1 && numCount >= 2;
            return (
              <CardFrame
                key={c.id}
                stacked={narrow}
                card={c}
                onChange={(p) => patch(c.id, p)}
                onFront={() => front(c.id)}
                onRemove={() => remove(c.id)}
                head={<EditableHead card={c} onChange={(p) => patch(c.id, p)} />}
                actions={
                  <button
                    type="button"
                    onClick={() => void r?.refetch()}
                    title="Şimdi yeniden sorgula"
                    className="pano-press flex h-7 w-7 items-center justify-center rounded-md text-canvas-muted transition-colors hover:bg-slate-100 hover:text-canvas-ink"
                  >
                    <RotateCw className={['h-3.5 w-3.5', r?.isFetching ? 'animate-spin' : ''].join(' ')} />
                  </button>
                }
                toolbar={
                  <>
                      <ToolSelect value={c.chart} title="Grafik tipi" onChange={(v) => patch(c.id, { chart: v as ChartKind })}>
                        {options.map((o) => (
                          <option key={o} value={o}>
                            {CHART_LABEL[o]}
                          </option>
                        ))}
                      </ToolSelect>
                      {['column', 'bar', 'pie', 'donut'].includes(c.chart) && (
                        <button
                          type="button"
                          onClick={() => patch(c.id, { depth: !c.depth })}
                          title="Gerçek 3B görünüm (WebGL); fareyle döndürülür"
                          aria-pressed={Boolean(c.depth)}
                          className={[
                            'pano-press h-7 rounded-md border px-2 text-[11px] font-semibold transition-colors',
                            c.depth ? 'border-canvas-violet/30 bg-canvas-violet/10 text-canvas-violet' : 'border-slate-200 bg-white text-canvas-muted hover:border-slate-300',
                          ].join(' ')}
                        >
                          3B
                        </button>
                      )}
                      {isKpi && !compared && (
                        <ToolSelect
                          value=""
                          disabled={comparing === c.id}
                          onChange={(v) => {
                            const opt = COMPARE.find((k) => k.key === v);
                            if (opt) void compare(c, opt.label);
                          }}
                          title="Değeri önceki dönemle karşılaştır"
                        >
                          <option value="">{comparing === c.id ? 'Soruluyor…' : 'Karşılaştır…'}</option>
                          {COMPARE.map((k) => (
                            <option key={k.key} value={k.key}>
                              {k.label}
                            </option>
                          ))}
                        </ToolSelect>
                      )}
                      <ToolSelect
                        value={c.refresh ?? 'manual'}
                        title="Sunucu kartı kendiliğinden ne zaman tazelesin"
                        icon={<Timer className="h-3 w-3 text-canvas-muted" />}
                        onChange={(v) =>
                          patch(c.id, {
                            refresh: v as BoardRefresh,
                            refreshAt: v === 'daily' ? c.refreshAt || '08:00' : null,
                          })
                        }
                      >
                        {(Object.keys(REFRESH_LABEL) as BoardRefresh[]).map((k) => (
                          <option key={k} value={k}>
                            {REFRESH_LABEL[k]}
                          </option>
                        ))}
                      </ToolSelect>
                      {c.refresh === 'daily' && (
                        <input
                          type="time"
                          value={c.refreshAt || '08:00'}
                          onChange={(e) => patch(c.id, { refreshAt: e.target.value || '08:00' })}
                          title="Günlük tazeleme saati"
                          className="h-7 w-[84px] rounded-md border border-slate-200 bg-white px-1.5 text-[11px] font-semibold tabular-nums outline-none hover:border-slate-300"
                        />
                      )}
                      {r?.isError && (
                        <span className="text-[11px] font-bold text-red-600" title={r.error instanceof Error ? r.error.message : ''}>
                          veri gelmedi
                        </span>
                      )}
                      {r?.data?.truncated && (
                        <span className="text-[11px] font-bold text-amber-600" title="Sonuç motorun satır sınırında kesildi">
                          ilk {rows.length.toLocaleString('tr-TR')} satır
                        </span>
                      )}
                  </>
                }
                foot={
                  <>
                    <span
                      className="flex min-w-0 items-center gap-1 text-[11px] font-semibold text-canvas-muted"
                      title="Bu kartın verisinin en son ne zaman sorgulandığı"
                    >
                      <Clock className="h-3 w-3 shrink-0" />
                      {r?.isFetching ? (
                        <span className="text-canvas-violet">Sorgulanıyor…</span>
                      ) : (
                        <span className="truncate tabular-nums">Son sorgu {stamp(r?.dataUpdatedAt)}</span>
                      )}
                      {rows.length > 0 && !r?.isFetching && (
                        <span className="hidden sm:inline">· {rows.length.toLocaleString('tr-TR')} satır</span>
                      )}
                    </span>
                    <span className="pano-noprint flex items-center gap-0.5">
                      <button
                        type="button"
                        disabled={!rows.length}
                        onClick={() => download(fileName(c.title, 'csv'), toCsv(cols, rows))}
                        title="Bu kartın verisini CSV (Excel) olarak indir"
                        className="pano-press flex h-8 items-center gap-1 rounded-lg px-2 text-[11px] font-bold text-canvas-muted transition-colors hover:bg-slate-100 hover:text-canvas-ink disabled:opacity-50"
                      >
                        <Download className="h-3.5 w-3.5" />
                        CSV
                      </button>
                      <button
                        type="button"
                        disabled={exporting != null}
                        onClick={() => void exportExcel([c.id], c.id)}
                        title="Bu kartı Excel olarak indir: tam veri, biçimli tablo ve grafik"
                        className="pano-press flex h-8 items-center gap-1 rounded-lg px-2 text-[11px] font-bold text-canvas-muted transition-colors hover:bg-slate-100 hover:text-canvas-ink disabled:opacity-50"
                      >
                        {exporting === c.id ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <FileSpreadsheet className="h-3.5 w-3.5" />}
                        Excel
                      </button>
                      <button
                        type="button"
                        onClick={() => patch(c.id, { sqlOpen: !sqlOpen })}
                        aria-expanded={sqlOpen}
                        className={[
                          'pano-press flex h-8 items-center gap-1 rounded-lg px-2 text-[11px] font-bold transition-colors',
                          sqlOpen ? 'bg-slate-900 text-white' : 'text-canvas-muted hover:bg-slate-100 hover:text-canvas-ink',
                        ].join(' ')}
                      >
                        <Code2 className="h-3.5 w-3.5" />
                        SQL
                        <ChevronDown
                          className={['h-3 w-3 transition-transform duration-200 ease-[cubic-bezier(0.77,0,0.175,1)]', sqlOpen ? 'rotate-180' : ''].join(' ')}
                        />
                      </button>
                    </span>
                  </>
                }
              >
                <div
                  className={[
                    'pano-plot',
                    printing ? (c.chart === 'table' ? 'pano-plot-table' : 'h-[300px] shrink-0') : narrow ? 'h-[240px] shrink-0' : 'min-h-0 flex-1',
                  ].join(' ')}
                >
                  {r?.isLoading ? (
                    <div className="flex h-full items-center justify-center text-canvas-muted">
                      <Loader2 className="h-4 w-4 animate-spin" />
                    </div>
                  ) : (
                    <Chart kind={c.chart} cols={cols} rows={rows} depth={printing ? false : c.depth} still={printing} />
                  )}
                </div>
                {sqlOpen && !printing && <SqlPanel sql={c.sql} className="pano-noprint mt-2 h-[152px] shrink-0" />}
              </CardFrame>
            );
          })}
        </div>
      </main>

      {/* Önizleme + soru çubuğu */}
      <div className="pano-noprint absolute bottom-3 left-14 right-2 sm:bottom-6 sm:left-[92px] sm:right-6 z-40 flex justify-center">
        <div className="w-full max-w-[980px]">
          {pending && (
            <div
              key={pending.at}
              className="pano-rise mb-3 flex max-h-[72vh] flex-col overflow-hidden rounded-2xl sm:rounded-3xl border border-white bg-white shadow-canvas-card ring-1 ring-slate-900/5"
            >
              <div className="min-h-0 flex-1 overflow-auto p-3 sm:p-4">
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <div className="text-[11px] font-extrabold uppercase tracking-wide text-canvas-violet">Sonuç hazır</div>
                    <div className="truncate text-[13px] font-extrabold" title={pending.title}>
                      {pending.title}
                    </div>
                    <div className="text-[11px] text-canvas-muted">
                      {pending.rows.length} satır · {pending.cols.length} kolon · önizleme · {stamp(pending.at)}
                    </div>
                  </div>
                  <button
                    type="button"
                    onClick={() => setPending(null)}
                    title="Vazgeç"
                    className="pano-press flex h-9 w-9 shrink-0 items-center justify-center rounded-xl text-canvas-muted transition-colors hover:bg-slate-100"
                  >
                    <X className="h-4 w-4" />
                  </button>
                </div>

                {/* Grafik tipi: eklemeden önce seçilir, kart onunla doğar. */}
                <div className="mt-2 flex flex-wrap gap-1">
                  {pendingAllowed.map((k) => (
                    <button
                      key={k}
                      type="button"
                      onClick={() => setPending({ ...pending, chart: k })}
                      aria-pressed={pending.chart === k}
                      className={[
                        'pano-press h-8 rounded-lg px-2.5 text-[11px] font-bold transition-colors',
                        pending.chart === k ? 'bg-canvas-violet text-white' : 'bg-slate-100 text-canvas-muted hover:bg-slate-200 hover:text-canvas-ink',
                      ].join(' ')}
                    >
                      {CHART_LABEL[k]}
                    </button>
                  ))}
                </div>

                <div className="mt-2 h-[200px] sm:h-[260px]">
                  <Chart kind={pending.chart} cols={pending.cols} rows={pending.rows} depth={false} />
                </div>

                <button
                  type="button"
                  onClick={() => setPendingSql((v) => !v)}
                  aria-expanded={pendingSql}
                  className="pano-press mt-2 flex h-8 items-center gap-1 rounded-lg px-2 text-[11px] font-bold text-canvas-muted transition-colors hover:bg-slate-100 hover:text-canvas-ink"
                >
                  <Code2 className="h-3.5 w-3.5" />
                  {pendingSql ? "SQL'i gizle" : "Çalışan SQL'i göster"}
                  <ChevronDown
                    className={['h-3 w-3 transition-transform duration-200 ease-[cubic-bezier(0.77,0,0.175,1)]', pendingSql ? 'rotate-180' : ''].join(' ')}
                  />
                </button>
                {pendingSql && <SqlPanel sql={pending.sql} className="mt-1 h-[160px]" />}
              </div>

              {/* Büyük çağrı: sonucu panoya sabitle. */}
              <div className="flex items-center gap-2 border-t border-slate-100 bg-gradient-to-r from-canvas-coral/10 via-white to-canvas-violet/10 p-3 sm:p-4">
                <button
                  type="button"
                  onClick={() => void addPending()}
                  className="pano-cta pano-press flex h-12 min-w-0 flex-1 items-center justify-center gap-2 rounded-2xl bg-gradient-to-r from-canvas-coral to-canvas-violet px-5 text-[14px] font-extrabold text-white shadow-lg shadow-canvas-violet/30 sm:h-14 sm:text-[15px]"
                >
                  <Plus className="h-5 w-5" />
                  Panoya ekle
                  <span className="hidden font-semibold text-white/80 sm:inline">· {CHART_LABEL[pending.chart]} olarak</span>
                </button>
                <button
                  type="button"
                  onClick={() => setPending(null)}
                  className="pano-press h-12 shrink-0 rounded-2xl px-4 text-[12px] font-bold text-canvas-muted transition-colors hover:bg-slate-100 sm:h-14"
                >
                  Vazgeç
                </button>
              </div>
            </div>
          )}

          {err && (
            <div className="glass-card mb-3 flex items-start justify-between gap-2 rounded-2xl px-4 py-2.5 text-[12px] font-semibold text-red-700 shadow-canvas-card">
              <span>{err}</span>
              <button type="button" onClick={() => setErr(null)} aria-label="Kapat" className="pano-press shrink-0 rounded-lg p-1 hover:bg-red-50">
                <X className="h-3.5 w-3.5" />
              </button>
            </div>
          )}

          <form
            onSubmit={(e) => {
              e.preventDefault();
              void ask();
            }}
            className="glass-dock flex items-center gap-3 rounded-3xl p-2.5 shadow-dock-shadow"
          >
            <div className="flex min-w-0 flex-1 items-center rounded-2xl border border-slate-200/80 bg-white/90 px-4 py-2">
              <input
                value={prompt}
                onChange={(e) => setPrompt(e.target.value)}
                placeholder="Panoya eklemek için sorun… örn. aylara göre net ciro"
                className="w-full bg-transparent text-xs font-semibold text-canvas-ink outline-none placeholder:text-canvas-muted/70"
              />
            </div>
            <button
              type="submit"
              disabled={asking || !prompt.trim()}
              aria-label="Gönder"
              className="pano-press flex h-11 w-11 sm:h-9 sm:w-9 items-center justify-center rounded-xl bg-gradient-to-tr from-canvas-coral to-canvas-violet text-white shadow-md transition-opacity disabled:opacity-60"
            >
              {asking ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
            </button>
          </form>
        </div>
      </div>
    </Shell>
  );
}
