import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useQueries, useQuery, useQueryClient } from '@tanstack/react-query';
import { Box, Check, ChevronDown, Clock, Code2, Copy, GripVertical, Loader2, Plus, RotateCw, Send, Trash2, X } from 'lucide-react';
import { ENGINE_BASE, ENGINE_ENABLED, EngineAuthError, ask as askEngine, runSql, type SqlResult } from '../engine';
import { stamp } from '../format';
import Chart, { CHART_LABEL, allowedCharts, suggestChart, type Col, type Row } from './Chart';
import {
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

function CardFrame({
  card,
  onChange,
  onFront,
  onRemove,
  children,
  head,
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
      style={
        stacked
          ? { height: Math.min(live?.h ?? card.h, 380) + (card.sqlOpen ? SQL_EXTRA : 0) }
          : { left: card.x, top: card.y, width: w, height: h, transform: shift, zIndex: mode ? 999 : (card.z ?? 20) }
      }
      onPointerDown={stacked ? undefined : (e) => down(e, 'move')}
      onPointerMove={stacked ? undefined : move}
      onPointerUp={stacked ? undefined : up}
      onPointerCancel={stacked ? undefined : up}
    >
      <div className="glass-card pano-card flex h-full flex-col rounded-[22px] p-3 shadow-canvas-card sm:p-4">
        <div className={['flex items-start gap-2 border-b border-slate-100 pb-2', stacked ? '' : 'pano-handle cursor-grab'].join(' ')}>
          {!stacked && (
            <span
              className="mt-0.5 shrink-0 rounded-md p-0.5 text-slate-300 transition-colors group-hover/card:text-slate-400"
              title="Sürükleyip taşı"
              aria-hidden
            >
              <GripVertical className="h-4 w-4" />
            </span>
          )}
          <div className="min-w-0 flex-1">{head}</div>
          <button
            type="button"
            onClick={onRemove}
            title="Karttan çıkar"
            className="pano-press flex h-8 w-8 shrink-0 items-center justify-center rounded-lg text-canvas-muted transition-colors hover:bg-red-50 hover:text-red-600 md:opacity-0 md:group-hover/card:opacity-100 md:focus-visible:opacity-100"
          >
            <Trash2 className="h-3.5 w-3.5" />
          </button>
        </div>
        <div className="flex min-h-0 flex-1 flex-col pt-2">{children}</div>
        <div className="mt-2 flex flex-wrap items-center justify-between gap-x-3 gap-y-1 border-t border-slate-100 pt-2">{foot}</div>
      </div>
      {!stacked && (
        <span
          onPointerDown={(e) => down(e, 'size')}
          onPointerMove={move}
          onPointerUp={up}
          onPointerCancel={up}
          title="Boyutlandır"
          className="absolute -bottom-1 -right-1 h-5 w-5 cursor-nwse-resize rounded-full border-2 border-white bg-slate-300/90 opacity-0 shadow transition-opacity hover:bg-canvas-violet group-hover/card:opacity-100"
        />
      )}
    </div>
  );
}

type Pending = { title: string; sql: string; cols: Col[]; rows: Row[]; chart: ChartKind; at: number };

/**
 * Kişiye özel pano. Soru sorulur, gelen sonuç grafiğe çevrilir, "Panoya ekle"
 * denince kart olarak sabitlenir. Kartlar taşınır, boyutlandırılır, tipi
 * değiştirilir; konumları kullanıcı adına kaydedilir.
 *
 * Kart verisi donmuş değildir: saklanan şey SQL'dir, açılışta yeniden koşar.
 */
export default function BoardScreen() {
  const user = useUser();
  const [cards, setCards] = useState<BoardCard[]>([]);
  const [prompt, setPrompt] = useState('');
  const [pending, setPending] = useState<Pending | null>(null);
  const [pendingSql, setPendingSql] = useState(false);
  const [asking, setAsking] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    setCards(loadBoard(user));
  }, [user]);

  const persist = useCallback(
    (next: BoardCard[]) => {
      setCards(next);
      saveBoard(user, next);
    },
    [user],
  );

  const qc = useQueryClient();
  // Kayıtlı olan SQL'dir. Kart önce son sonucuyla anında çizilir; sonuç
  // beş dakikadan eskiyse sorgu arka planda koşar ve kart kendini tazeler.
  const cached = useMemo(() => loadResults(user), [user]);
  const results = useQueries({
    queries: cards.map((c) => {
      const hit = cached[c.id];
      return {
        queryKey: ['pano', c.id, c.sql],
        queryFn: async () => {
          const r = await runSql<Row>(c.sql);
          saveResult(user, c.id, { ...(r as CardResult), at: Date.now() });
          return r;
        },
        initialData: hit ? (hit as unknown as SqlResult<Row>) : undefined,
        initialDataUpdatedAt: hit?.at,
        enabled: ENGINE_ENABLED && Boolean(c.sql),
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
        setErr(a.summary || a.explanation || 'Motor bu soruya tablo döndürmedi.');
      } else {
        setPending({ title: q, sql: a.sql, cols, rows, chart: suggestChart(cols, rows), at: Date.now() });
      }
    } catch (e) {
      setErr(e instanceof EngineAuthError ? 'Oturum gerekli.' : 'Motor yanıt vermedi.');
    } finally {
      setAsking(false);
    }
  };

  const addPending = () => {
    if (!pending) return;
    const slot = nextSlot(cards);
    const card: BoardCard = {
      id: newId(),
      title: pending.title,
      sql: pending.sql,
      chart: pending.chart,
      depth: false,
      z: topZ(cards),
      createdAt: new Date().toISOString(),
      ...slot,
    };
    persist([...cards, card]);
    // Önizleme ilk 50 satırdır; kart onunla hemen çizilir ama bayat sayılır ve tam sonuç hemen istenir.
    const seed = { columns: pending.cols, records: pending.rows } as SqlResult<Row>;
    qc.setQueryData(['pano', card.id, card.sql], seed, { updatedAt: pending.at });
    saveResult(user, card.id, { ...(seed as unknown as CardResult), at: pending.at });
    void qc.invalidateQueries({ queryKey: ['pano', card.id, card.sql] });
    setPending(null);
    setPendingSql(false);
    setPrompt('');
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
    persist(cards.filter((c) => c.id !== id));
  };

  const height = useMemo(() => Math.max(720, ...cards.map((c) => c.y + c.h + 40)), [cards]);

  const narrow = useNarrow();
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
      {/* Kartlar */}
      <main className="absolute bottom-[152px] left-14 right-2 top-16 sm:bottom-[118px] sm:left-[92px] sm:right-6 sm:top-[84px] overflow-auto">
        <div
          className={narrow ? 'mx-auto flex w-full flex-col gap-3 pb-3' : 'relative mx-auto w-full max-w-[1760px]'}
          style={narrow ? undefined : { height }}
        >
          {!cards.length && !pending && (
            <div className="flex h-[420px] flex-col items-center justify-center text-center">
              <div className="glass-card rounded-3xl px-8 py-7 shadow-canvas-card">
                <Box className="mx-auto h-7 w-7 text-canvas-violet" />
                <h2 className="mt-3 text-base font-extrabold">Panonuz boş</h2>
                <p className="mt-1.5 max-w-[340px] text-[12.5px] leading-snug text-canvas-muted">
                  Aşağıya bir soru yazın. Gelen sonucu beğenirseniz “Panoya ekle” deyin, kart burada sabit kalsın.
                  Kartları başlığından tutup sürükleyebilir, köşesinden büyütebilirsiniz.
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
            return (
              <CardFrame
                key={c.id}
                stacked={narrow}
                card={c}
                onChange={(p) => patch(c.id, p)}
                onFront={() => front(c.id)}
                onRemove={() => remove(c.id)}
                head={
                  <>
                    <div className="truncate text-[12.5px] font-extrabold" title={c.title}>
                      {c.title}
                    </div>
                    <div className="mt-1 flex flex-wrap items-center gap-1.5">
                      <select
                        value={c.chart}
                        onChange={(e) => patch(c.id, { chart: e.target.value as ChartKind })}
                        className="rounded-lg border border-slate-200 bg-white px-1.5 py-0.5 text-[11px] font-bold text-canvas-muted outline-none"
                      >
                        {options.map((o) => (
                          <option key={o} value={o}>
                            {CHART_LABEL[o]}
                          </option>
                        ))}
                      </select>
                      {['column', 'bar', 'pie', 'donut'].includes(c.chart) && (
                        <button
                          type="button"
                          onClick={() => patch(c.id, { depth: !c.depth })}
                          className={[
                            'pano-press rounded-lg px-1.5 py-0.5 text-[11px] font-bold transition-colors',
                            c.depth ? 'bg-canvas-violet/15 text-canvas-violet' : 'text-canvas-muted hover:bg-slate-100',
                          ].join(' ')}
                        >
                          3B
                        </button>
                      )}
                      <button
                        type="button"
                        onClick={() => void r?.refetch()}
                        title="Şimdi yeniden sorgula"
                        className="pano-press rounded-lg p-1 text-canvas-muted transition-colors hover:bg-slate-100"
                      >
                        <RotateCw className={['h-3 w-3', r?.isFetching ? 'animate-spin' : ''].join(' ')} />
                      </button>
                      {r?.isError && <span className="text-[11px] font-bold text-red-600">veri gelmedi</span>}
                      {r?.data?.truncated && (
                        <span className="text-[11px] font-bold text-amber-600" title="Sonuç motorun satır sınırında kesildi">
                          ilk {rows.length.toLocaleString('tr-TR')} satır
                        </span>
                      )}
                    </div>
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
                      <ChevronDown className={['h-3 w-3 transition-transform duration-200', sqlOpen ? 'rotate-180' : ''].join(' ')} />
                    </button>
                  </>
                }
              >
                <div className="min-h-0 flex-1">
                  {r?.isLoading ? (
                    <div className="flex h-full items-center justify-center text-canvas-muted">
                      <Loader2 className="h-4 w-4 animate-spin" />
                    </div>
                  ) : (
                    <Chart kind={c.chart} cols={cols} rows={rows} depth={c.depth} />
                  )}
                </div>
                {sqlOpen && <SqlPanel sql={c.sql} className="mt-2 h-[152px] shrink-0" />}
              </CardFrame>
            );
          })}
        </div>
      </main>

      {/* Önizleme + soru çubuğu */}
      <div className="absolute bottom-3 left-14 right-2 sm:bottom-6 sm:left-[92px] sm:right-6 z-40 flex justify-center">
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
                  {pendingSql ? 'SQL\'i gizle' : 'Çalışan SQL\'i göster'}
                  <ChevronDown className={['h-3 w-3 transition-transform duration-200', pendingSql ? 'rotate-180' : ''].join(' ')} />
                </button>
                {pendingSql && <SqlPanel sql={pending.sql} className="mt-1 h-[160px]" />}
              </div>

              {/* Büyük çağrı: sonucu panoya sabitle. */}
              <div className="flex items-center gap-2 border-t border-slate-100 bg-gradient-to-r from-canvas-coral/10 via-white to-canvas-violet/10 p-3 sm:p-4">
                <button
                  type="button"
                  onClick={addPending}
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
            <div className="glass-card mb-3 rounded-2xl px-4 py-2.5 text-[12px] font-semibold text-red-700 shadow-canvas-card">
              {err}
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
