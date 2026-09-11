import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useQueries, useQuery } from '@tanstack/react-query';
import { Box, Loader2, Plus, RotateCw, Send, Trash2, X } from 'lucide-react';
import { ENGINE_BASE, ENGINE_ENABLED, EngineAuthError, ask as askEngine, runSql } from '../engine';
import Chart, { CHART_LABEL, allowedCharts, suggestChart, type Col, type Row } from './Chart';
import { loadBoard, newId, nextSlot, saveBoard, type BoardCard, type ChartKind } from './store';
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

const INTERACTIVE = 'a, button, input, select, textarea';

/** Taşınabilir ve boyutlandırılabilir pano kartı. */
function CardFrame({
  card,
  onChange,
  onRemove,
  children,
  head,
}: {
  card: BoardCard;
  onChange: (patch: Partial<BoardCard>) => void;
  onRemove: () => void;
  children: React.ReactNode;
  head: React.ReactNode;
}) {
  const [live, setLive] = useState<Partial<BoardCard> | null>(null);
  const mode = useRef<'move' | 'size' | null>(null);
  const start = useRef({ x: 0, y: 0, cx: 0, cy: 0, w: 0, h: 0 });
  const b = { ...card, ...(live ?? {}) };

  const down = (e: React.PointerEvent, m: 'move' | 'size') => {
    if (m === 'move' && (e.target as HTMLElement).closest(INTERACTIVE)) return;
    e.stopPropagation();
    mode.current = m;
    start.current = { x: e.clientX, y: e.clientY, cx: card.x, cy: card.y, w: card.w, h: card.h };
    (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
  };
  const move = (e: React.PointerEvent) => {
    if (!mode.current) return;
    const dx = e.clientX - start.current.x;
    const dy = e.clientY - start.current.y;
    if (mode.current === 'move') {
      setLive({ x: Math.max(0, start.current.cx + dx), y: Math.max(0, start.current.cy + dy) });
    } else {
      setLive({ w: Math.max(260, start.current.w + dx), h: Math.max(180, start.current.h + dy) });
    }
  };
  const up = () => {
    if (live) onChange(live);
    setLive(null);
    mode.current = null;
  };

  return (
    <div
      className="group/card absolute cursor-grab active:cursor-grabbing"
      style={{ left: b.x, top: b.y, width: b.w, height: b.h, zIndex: mode.current ? 50 : 20 }}
      onPointerDown={(e) => down(e, 'move')}
      onPointerMove={move}
      onPointerUp={up}
      onPointerCancel={up}
    >
      <div className="glass-card flex h-full flex-col rounded-[22px] p-4 shadow-canvas-card">
        <div className="flex items-start justify-between gap-2 border-b border-slate-100 pb-2">
          <div className="min-w-0 flex-1">{head}</div>
          <button
            type="button"
            onClick={onRemove}
            title="Karttan çıkar"
            className="shrink-0 rounded-lg p-1 text-canvas-muted opacity-0 transition hover:bg-red-50 hover:text-red-600 group-hover/card:opacity-100"
          >
            <Trash2 className="h-3.5 w-3.5" />
          </button>
        </div>
        <div className="min-h-0 flex-1 pt-2">{children}</div>
      </div>
      <span
        onPointerDown={(e) => down(e, 'size')}
        onPointerMove={move}
        onPointerUp={up}
        title="Boyutlandır"
        className="absolute -bottom-1 -right-1 h-4 w-4 cursor-nwse-resize rounded-full border border-white bg-slate-300/90 opacity-0 shadow transition hover:bg-canvas-violet group-hover/card:opacity-100"
      />
    </div>
  );
}

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
  const [pending, setPending] = useState<{ title: string; sql: string; cols: Col[]; rows: Row[] } | null>(null);
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

  // Kayıtlı olan SQL'dir: kartlar her açılışta yeniden koşar, rakam bayatlamaz.
  const results = useQueries({
    queries: cards.map((c) => ({
      queryKey: ['pano', c.id, c.sql],
      queryFn: () => runSql<Row>(c.sql),
      enabled: ENGINE_ENABLED && Boolean(c.sql),
      staleTime: 5 * 60_000,
      retry: false,
    })),
  });

  const ask = async () => {
    const q = prompt.trim();
    if (!q || !ENGINE_ENABLED) return;
    setAsking(true);
    setErr(null);
    setPending(null);
    try {
      const a = await askEngine(q);
      const cols = (a.columns ?? []) as Col[];
      const rows = (a.records ?? []) as Row[];
      if (!a.sql || !rows.length) {
        setErr(a.summary || a.explanation || 'Motor bu soruya tablo döndürmedi.');
      } else {
        setPending({ title: q, sql: a.sql, cols, rows });
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
      chart: suggestChart(pending.cols, pending.rows),
      depth: false,
      createdAt: new Date().toISOString(),
      ...slot,
    };
    persist([...cards, card]);
    setPending(null);
    setPrompt('');
  };

  const patch = (id: string, p: Partial<BoardCard>) => persist(cards.map((c) => (c.id === id ? { ...c, ...p } : c)));
  const remove = (id: string) => persist(cards.filter((c) => c.id !== id));

  const height = useMemo(() => Math.max(720, ...cards.map((c) => c.y + c.h + 40)), [cards]);

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
      <main className="absolute inset-x-0 bottom-[118px] top-[84px] overflow-auto px-6">
        <div className="relative mx-auto w-full max-w-[1760px]" style={{ height }}>
          {!cards.length && !pending && (
            <div className="flex h-[420px] flex-col items-center justify-center text-center">
              <div className="glass-card rounded-3xl px-8 py-7 shadow-canvas-card">
                <Box className="mx-auto h-7 w-7 text-canvas-violet" />
                <h2 className="mt-3 text-base font-extrabold">Panonuz boş</h2>
                <p className="mt-1.5 max-w-[340px] text-[12.5px] leading-snug text-canvas-muted">
                  Aşağıya bir soru yazın. Gelen sonucu beğenirseniz “Panoya ekle” deyin, kart burada sabit kalsın.
                </p>
              </div>
            </div>
          )}

          {cards.map((c, i) => {
            const r = results[i];
            const cols = (r?.data?.columns ?? []) as Col[];
            const rows = (r?.data?.records ?? []) as Row[];
            const options = allowedCharts(cols, rows);
            return (
              <CardFrame
                key={c.id}
                card={c}
                onChange={(p) => patch(c.id, p)}
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
                        className="rounded-lg border border-slate-200 bg-white px-1.5 py-0.5 text-[10.5px] font-bold text-canvas-muted outline-none"
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
                            'rounded-lg px-1.5 py-0.5 text-[10.5px] font-bold transition',
                            c.depth ? 'bg-canvas-violet/15 text-canvas-violet' : 'text-canvas-muted hover:bg-slate-100',
                          ].join(' ')}
                        >
                          3B
                        </button>
                      )}
                      <button
                        type="button"
                        onClick={() => r?.refetch()}
                        title="Yenile"
                        className="rounded-lg p-0.5 text-canvas-muted transition hover:bg-slate-100"
                      >
                        <RotateCw className={['h-3 w-3', r?.isFetching ? 'animate-spin' : ''].join(' ')} />
                      </button>
                      {r?.isError && <span className="text-[10px] font-bold text-red-600">veri gelmedi</span>}
                    </div>
                  </>
                }
              >
                {r?.isLoading ? (
                  <div className="flex h-full items-center justify-center text-canvas-muted">
                    <Loader2 className="h-4 w-4 animate-spin" />
                  </div>
                ) : (
                  <Chart kind={c.chart} cols={cols} rows={rows} depth={c.depth} />
                )}
              </CardFrame>
            );
          })}
        </div>
      </main>

      {/* Önizleme + soru çubuğu */}
      <div className="absolute inset-x-0 bottom-6 z-40 flex justify-center px-6">
        <div className="w-full max-w-[980px]">
          {pending && (
            <div className="glass-card mb-3 rounded-3xl p-4 shadow-canvas-card">
              <div className="flex items-center justify-between gap-3">
                <div className="min-w-0">
                  <div className="truncate text-[12.5px] font-extrabold">{pending.title}</div>
                  <div className="text-[11px] text-canvas-muted">
                    {pending.rows.length} satır · {pending.cols.length} kolon · önizleme
                  </div>
                </div>
                <div className="flex shrink-0 items-center gap-2">
                  <button
                    type="button"
                    onClick={addPending}
                    className="flex items-center gap-1.5 rounded-xl bg-gradient-to-r from-canvas-coral to-canvas-violet px-4 py-2 text-[12px] font-extrabold text-white shadow-md"
                  >
                    <Plus className="h-3.5 w-3.5" />
                    Panoya ekle
                  </button>
                  <button
                    type="button"
                    onClick={() => setPending(null)}
                    className="rounded-xl p-2 text-canvas-muted transition hover:bg-slate-100"
                  >
                    <X className="h-4 w-4" />
                  </button>
                </div>
              </div>
              <div className="mt-2 h-[190px]">
                <Chart kind={suggestChart(pending.cols, pending.rows)} cols={pending.cols} rows={pending.rows} depth={false} />
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
              className="flex h-9 w-9 items-center justify-center rounded-xl bg-gradient-to-tr from-canvas-coral to-canvas-violet text-white shadow-md transition disabled:opacity-60"
            >
              {asking ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
            </button>
          </form>
        </div>
      </div>
    </Shell>
  );
}
