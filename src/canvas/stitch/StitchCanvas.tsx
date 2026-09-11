import { useLayoutEffect, useMemo, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import Shell from './Shell';
import Node, { LayoutProvider, useLayout, type BoxMap } from './layout';
import zekiGif from '@/assets/zeki-ai.gif';
import type { StitchCanvasData } from './data';

/**
 * Stitch ekranının (projects/13426839861607265553/screens/c35e1503…) birebir
 * kendisi. Markup design/stitch-wow/03-canvas.html'den mekanik olarak JSX'e
 * çevrildi: sınıf adları, sıralama, eğimler, bağlantı yolları, bant etiketi ve
 * mini harita aynen duruyor. Değişen tek şey metinlerin veriden gelmesi.
 *
 * Buraya elle düzen değişikliği YAPILMAZ. Tasarım değişecekse Stitch'te
 * değişir, dosya yeniden çevrilir.
 */
/** Kartların çizildiği alan. Tasarımdaki koordinatlar bu kutunun içinde;
 *  üst şerit, ray ve dock ekrana yapıştığı için kutu yalnız aradaki boşluğu
 *  doldurur. */
/** Tasarımdaki başlangıç yerleşimi. Kullanıcı taşıyınca üzerine yazılır. */
const DEFAULT_BOXES: BoxMap = {
  q: { x: 470, y: 8, w: 500 },
  c1: { x: 110, y: 108, w: 235 },
  c2: { x: 365, y: 103, w: 250 },
  c3: { x: 635, y: 118, w: 240 },
  c4: { x: 895, y: 103, w: 235 },
  c5: { x: 1150, y: 108, w: 215 },
  main: { x: 290, y: 378, w: 860 },
  sticker: { x: 1185, y: 378, w: 125 },
};


const ACCENTS = ['#FF6B4A', '#7C5CFF', '#10B981', '#F59E0B', '#6B7280'];

/** Sorudan kartlara giden eğriler. Kart taşınınca çizgi peşinden gelir. */
function Connectors() {
  const { boxes, tick } = useLayout();
  const paths = useMemo(() => {
    const q = boxes.q;
    if (!q) return [];
    const sx = q.x + q.w / 2;
    const sy = q.y + 74;
    return ['c1', 'c2', 'c3', 'c4', 'c5']
      .map((id, i) => {
        const b = boxes[id];
        if (!b) return null;
        const tx = b.x + b.w / 2;
        const ty = b.y - 6;
        const dx = tx - sx;
        const spread = Math.min(Math.abs(dx) * 0.55, 260);
        const c1x = sx + Math.sign(dx) * spread;
        const c2x = tx - Math.sign(dx) * Math.min(Math.abs(dx) * 0.25, 90);
        return {
          id,
          color: ACCENTS[i],
          d: `M ${sx.toFixed(1)} ${sy.toFixed(1)} C ${c1x.toFixed(1)} ${(sy - 4).toFixed(1)}, ${c2x.toFixed(1)} ${(ty - 48).toFixed(1)}, ${tx.toFixed(1)} ${ty.toFixed(1)}`,
          tx,
          ty,
        };
      })
      .filter((v): v is { id: string; color: string; d: string; tx: number; ty: number } => v != null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [boxes, tick]);

  return (
    <svg className="pointer-events-none absolute inset-0 z-10 h-full w-full" xmlns="http://www.w3.org/2000/svg">
      <defs>
        {paths.map((p) => (
          <linearGradient key={p.id} id={`cv-${p.id}`} x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stopColor={p.color} stopOpacity="0.6" />
            <stop offset="100%" stopColor={p.color} stopOpacity="0.15" />
          </linearGradient>
        ))}
      </defs>
      {paths.map((p) => (
        <g key={p.id}>
          <path d={p.d} fill="none" stroke={`url(#cv-${p.id})`} strokeWidth={2} strokeLinecap="round" className="flowing-line" />
          <circle cx={p.tx} cy={p.ty} r={4} fill={p.color} />
        </g>
      ))}
    </svg>
  );
}

export default function StitchCanvas(props: {
  d: StitchCanvasData;
  onAsk?: (q: string) => void;
  onZoom?: (delta: number) => void;
  zoom?: number;
  screen?: string;
}) {
  const stageRef = useRef<HTMLDivElement | null>(null);
  const [stageW, setStageW] = useState(0);
  useLayoutEffect(() => {
    const el = stageRef.current;
    if (!el) return;
    const measure = () => setStageW(el.clientWidth);
    measure();
    const ro = new ResizeObserver(measure);
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  return (
    <LayoutProvider screen={props.screen ?? 'default'} defaults={DEFAULT_BOXES} stageW={stageW}>
      <CanvasBody {...props} stageRef={stageRef} />
    </LayoutProvider>
  );
}

function CanvasBody({
  d,
  onAsk: onSubmitAsk,
  onZoom,
  zoom,
  stageRef,
}: {
  d: StitchCanvasData;
  onAsk?: (q: string) => void;
  onZoom?: (delta: number) => void;
  zoom?: number;
  screen?: string;
  stageRef: React.MutableRefObject<HTMLDivElement | null>;
}) {
  const { reset, dirty } = useLayout();

  const [ask, setAsk] = useState('');
  const [showSql, setShowSql] = useState(false);
  const onAsk = () => {
    const q = ask.trim();
    if (q) onSubmitAsk?.(q);
  };
  return (
    <Shell
      head={{
        tenant: d.tenant,
        section: d.section,
        crumb: d.crumb,
        source: d.source,
        presence: d.presence,
        zoom: d.zoom,
      }}
      rail={d.rail}
      onZoom={onZoom}
      onReset={dirty ? reset : undefined}
    >
    <main className="absolute inset-x-0 top-[84px] bottom-[92px] overflow-auto">
        <div ref={stageRef} className="relative mx-auto h-full min-h-[640px] w-full max-w-[1760px]" style={{ zoom: zoom ?? 1 }}>
    
      {/* SVG CURVED CONNECTOR LINES (Mind-map Constellation) */}
      <Connectors />
      

      {/* ================= CENTER CONSTELLATION CONTAINER ================= */}
      <div className="relative h-full w-full">
      
        {/* USER'S QUESTION BUBBLE (Center Top Anchor) */}
        <Node id="q" z={30} resizable={false} className="group/node">
        <div className="animate-float-slow">
          <div className="glass-panel px-6 py-3.5 rounded-full shadow-canvas-card border border-white flex items-center gap-3.5 ring-4 ring-white/40">
            <div className="w-10 h-10 rounded-full bg-gradient-to-tr from-amber-400 via-orange-400 to-rose-500 text-white font-bold text-sm flex items-center justify-center shadow-md">
              {d.q.initials}
            </div>
            <div>
              <div className="flex items-center gap-2">
                <span className="text-[11px] font-bold text-muted uppercase tracking-wider">{d.q.role}</span>
                <span className="text-[10px] text-muted/60">{d.q.at}</span>
              </div>
              <h1 className="text-base font-extrabold text-ink tracking-tight flex items-center gap-2">
                {d.q.text}
              </h1>
            </div>
            <span className="w-2.5 h-2.5 rounded-full bg-mintSuccess ring-4 ring-mintSuccess/20 ml-2" title="ZEKİ AI Analiz Etti"></span>
          </div>
        </div>

        {/* ================= 5 CONSTELLATION ANSWER CARDS ================= */}

        {/* CARD 1: Stok (Rotated -3°) */}
        </Node>

        <Node id="c1" tilt={-3} className="group/node">
        <div className="glass-card rounded-[24px] p-4 shadow-canvas-card">
          <div className="flex items-center justify-between pb-2 border-b border-slate-100">
            <div className="flex items-center gap-2">
              <span className="w-6 h-6 rounded-lg bg-coral/10 text-coral flex items-center justify-center text-xs font-bold">{d.c1.icon}</span>
              <span className="text-xs font-extrabold tracking-tight text-ink">{d.c1.title}</span>
            </div>
            <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-red-50 text-red-600 border border-red-100">{d.c1.badge}</span>
          </div>

          <div className="mt-3">
            <div className="flex items-baseline justify-between">
              <div className="text-2xl font-black text-coral tracking-tight">{d.c1.big}</div>
              <div className="text-xs font-bold text-muted">{d.c1.bigSuffix}</div>
            </div>
            <div className="text-xs text-ink/80 mt-0.5 font-semibold">{d.c1.subLabel} <span className="font-bold text-ink">{d.c1.subValue}</span></div>

            {/* Red-to-amber depletion progress bar */}
            <div className="mt-3 space-y-1">
              <div className="w-full bg-slate-100 h-2.5 rounded-full overflow-hidden p-0.5 border border-slate-200/60 flex">
                <div className="h-full rounded-full bg-gradient-to-r from-red-500 via-coral to-amberWarn" style={{ width: `${d.c1.pct}%` }}></div>
              </div>
              <div className="flex justify-between text-[10px] text-muted font-medium pt-0.5">
                <span>{d.c1.footL}</span>
                <span>{d.c1.footR}</span>
              </div>
            </div>

            <div className="mt-3 pt-2.5 border-t border-slate-100 text-[11px] text-muted flex items-center justify-between">
              <span>{d.c1.rowLabel}</span>
              <span className="font-bold text-ink">{d.c1.rowValue}</span>
            </div>
          </div>
        </div>

        </Node>

        {/* CARD 2: Talep Tahmini (Rotated +2°) */}
        <Node id="c2" tilt={2} className="group/node">
        <div className="glass-card rounded-[24px] p-4 shadow-canvas-card">
          <div className="flex items-center justify-between pb-2 border-b border-slate-100">
            <div className="flex items-center gap-2">
              <span className="w-6 h-6 rounded-lg bg-violet/10 text-violet flex items-center justify-center text-xs font-bold">📈</span>
              <span className="text-xs font-extrabold tracking-tight text-ink">{d.c2.title}</span>
            </div>
            <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-violet/10 text-violet border border-violet/20">{d.c2.badge}</span>
          </div>

          <div className="mt-3">
            <div className="flex items-baseline justify-between">
              <div>
                <div className="text-[11px] font-semibold text-muted">{d.c2.label}</div>
                <div className="text-2xl font-black text-ink tracking-tight">{d.c2.big} <span className="text-xs font-normal text-muted">{d.c2.unit}</span></div>
              </div>
              <div className="flex items-center text-xs font-bold text-mintSuccess bg-emerald-50 px-2 py-1 rounded-lg">
                <svg className="w-3.5 h-3.5 mr-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M13 7h8m0 0v8m0-8l-8 8-4-4-6 6" /></svg>
                {d.c2.delta}
              </div>
            </div>

            {/* Mini Area Chart Visual */}
            <div className="mt-2 h-16 w-full relative">
              <svg className="w-full h-full overflow-visible" viewBox="0 0 210 50">
                <defs>
                  <linearGradient id="areaGrad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="#7C5CFF" stopOpacity="0.35" />
                    <stop offset="100%" stopColor="#7C5CFF" stopOpacity="0.0" />
                  </linearGradient>
                </defs>
                {/* Spark area */}
                {d.c2.areaPath ? <path d={d.c2.areaPath} fill="url(#areaGrad)" /> : null}
                {d.c2.linePath ? <path d={d.c2.linePath} fill="none" stroke="#7C5CFF" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" /> : null}
                {/* Highlight dot */}
                {d.c2.linePath ? <circle cx={d.c2.dot[0]} cy={d.c2.dot[1]} r="3.5" fill="#7C5CFF" stroke="#FFFFFF" strokeWidth="2" /> : <text x="105" y="30" textAnchor="middle" fontSize="11" fill="#94a3b8">Veri yok</text>}
              </svg>
              <div className="flex justify-between text-[10.5px] text-muted font-semibold mt-1">
                <span>{d.c2.tick1}</span>
                <span>{d.c2.tick2}</span>
                <span className="text-violet font-bold">{d.c2.tick3}</span>
              </div>
            </div>

            <div className="mt-2.5 pt-2 border-t border-slate-100 text-[10px] text-muted">
              {d.c2.foot}
            </div>
          </div>
        </div>

        </Node>

        {/* CARD 3: Kanal Dağılımı (Rotated -1.5°) */}
        <Node id="c3" tilt={-1.5} className="group/node">
        <div className="glass-card rounded-[24px] p-4 shadow-canvas-card">
          <div className="flex items-center justify-between pb-2 border-b border-slate-100">
            <div className="flex items-center gap-2">
              <span className="w-6 h-6 rounded-lg bg-emerald-50 text-mintSuccess flex items-center justify-center text-xs font-bold">🍩</span>
              <span className="text-xs font-extrabold tracking-tight text-ink">{d.c3.title}</span>
            </div>
            <span className="text-[10px] font-bold text-muted">{d.c3.badge}</span>
          </div>

          <div className="mt-3 flex items-center gap-3">
            {/* Donut Graphic SVG */}
            <div className="relative w-16 h-16 shrink-0">
              <svg className="w-full h-full -rotate-90" viewBox="0 0 36 36">
                {/* Background Ring */}
                <circle cx="18" cy="18" r="14" fill="none" stroke="#F1F5F9" strokeWidth="4.5" />
                {/* Segments */}
                {/* Kitabevi zinciri 42% -> 87.96 * 0.42 = 36.9 */}
                <circle cx="18" cy="18" r="14" fill="none" stroke="#7C5CFF" strokeWidth="4.5" strokeDasharray={d.c3.arcs[0].dash} strokeDashoffset={d.c3.arcs[0].offset} />
                {/* Online 31% -> 87.96 * 0.31 = 27.2 */}
                <circle cx="18" cy="18" r="14" fill="none" stroke="#FF6B4A" strokeWidth="4.5" strokeDasharray={d.c3.arcs[1].dash} strokeDashoffset={d.c3.arcs[1].offset} />
                {/* Okul/Kurum 18% -> 15.8 */}
                <circle cx="18" cy="18" r="14" fill="none" stroke="#10B981" strokeWidth="4.5" strokeDasharray={d.c3.arcs[2].dash} strokeDashoffset={d.c3.arcs[2].offset} />
                {/* Diğer 9% -> 7.9 */}
                <circle cx="18" cy="18" r="14" fill="none" stroke="#F59E0B" strokeWidth="4.5" strokeDasharray={d.c3.arcs[3].dash} strokeDashoffset={d.c3.arcs[3].offset} />
              </svg>
              <div className="absolute inset-0 flex flex-col items-center justify-center text-[10px] font-black text-ink">
                {d.c3.center}
              </div>
            </div>

            {/* Channel Legend */}
            <div className="space-y-1 text-[11px] flex-1">
              <div className="flex items-center justify-between">
                <span className="flex items-center gap-1.5 text-muted truncate">
                  <span className="w-2 h-2 rounded-full bg-violet shrink-0"></span> {d.c3.rows[0].label}
                </span>
                <span className="font-bold text-ink">{d.c3.rows[0].value}</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="flex items-center gap-1.5 text-muted truncate">
                  <span className="w-2 h-2 rounded-full bg-coral shrink-0"></span> {d.c3.rows[1].label}
                </span>
                <span className="font-bold text-ink">{d.c3.rows[1].value}</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="flex items-center gap-1.5 text-muted truncate">
                  <span className="w-2 h-2 rounded-full bg-mintSuccess shrink-0"></span> {d.c3.rows[2].label}
                </span>
                <span className="font-bold text-ink">{d.c3.rows[2].value}</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="flex items-center gap-1.5 text-muted truncate">
                  <span className="w-2 h-2 rounded-full bg-amberWarn shrink-0"></span> {d.c3.rows[3].label}
                </span>
                <span className="font-bold text-ink">{d.c3.rows[3].value}</span>
              </div>
            </div>
          </div>

          <div className="mt-2.5 pt-2 border-t border-slate-100 text-[10px] text-muted flex justify-between">
            <span>{d.c3.footLabel}</span>
            <span className="font-semibold text-ink">{d.c3.footValue}</span>
          </div>
        </div>

        </Node>

        {/* CARD 4: Telif Etkisi (Rotated +1°) */}
        <Node id="c4" tilt={1} className="group/node">
        <div className="glass-card rounded-[24px] p-4 shadow-canvas-card">
          <div className="flex items-center justify-between pb-2 border-b border-slate-100">
            <div className="flex items-center gap-2">
              <span className="w-6 h-6 rounded-lg bg-amber-50 text-amberWarn flex items-center justify-center text-xs font-bold">✍️</span>
              <span className="text-xs font-extrabold tracking-tight text-ink">{d.c4.title}</span>
            </div>
            <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-amber-50 text-amber-700 border border-amber-200/60">{d.c4.badge}</span>
          </div>

          <div className="mt-3">
            <div className="flex items-center gap-2.5">
              <div className="w-8 h-8 rounded-full bg-purple-100 text-purple-700 font-bold text-xs flex items-center justify-center ring-1 ring-purple-300">
                {d.c4.initials}
              </div>
              <div>
                <div className="text-xs font-bold text-ink">{d.c4.name}</div>
                <div className="text-[10px] text-muted">{d.c4.sub}</div>
              </div>
            </div>

            <div className="mt-3 bg-slate-50/80 p-2.5 rounded-xl border border-slate-100">
              <div className="text-[11px] text-muted font-medium">{d.c4.valueLabel}</div>
              <div className="text-xl font-black text-ink tracking-tight">{d.c4.value}</div>
              <div className="text-[10px] text-amber-700 font-semibold mt-1 flex items-center gap-1">
                <svg className="w-3 h-3 text-amberWarn" fill="currentColor" viewBox="0 0 20 20"><path fillRule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7-4a1 1 0 11-2 0 1 1 0 012 0zM9 9a1 1 0 000 2v3a1 1 0 001 1h1a1 1 0 100-2v-3a1 1 0 00-1-1H9z" clipRule="evenodd" /></svg>
                {d.c4.note}
              </div>
            </div>

            <div className="mt-2 text-[10px] text-muted flex justify-between">
              <span>{d.c4.footLabel}</span>
              <span className="font-bold text-mintSuccess">{d.c4.footValue}</span>
            </div>
          </div>
        </div>

        </Node>

        {/* CARD 5: Kanıt / Veri Dayanağı (Rotated +2.5°) */}
        <Node id="c5" tilt={2.5} className="group/node">
        <div className="glass-card rounded-[24px] p-4 shadow-canvas-card">
          <div className="flex items-center justify-between pb-2 border-b border-slate-100">
            <div className="flex items-center gap-2">
              <span className="w-6 h-6 rounded-lg bg-slate-100 text-slate-700 flex items-center justify-center text-xs font-bold">🔍</span>
              <span className="text-xs font-extrabold tracking-tight text-ink">{d.c5.title}</span>
            </div>
            {/* Tiny Sample Data Chip Inside Kanıt Card as requested */}
            <span className="text-[10.5px] font-bold px-1.5 py-0.5 rounded bg-slate-100 text-muted border border-slate-200">{d.c5.badge}</span>
          </div>

          <div className="mt-3 space-y-2">
            <div className={showSql ? 'text-[10px] font-mono text-ink break-all max-h-24 overflow-auto' : 'text-xs font-bold text-ink'}>
            {d.c5.summary}
          </div>

            <div className="space-y-1.5 pt-1">
              <div className="flex items-center justify-between text-[11px] p-1.5 bg-white rounded-lg border border-slate-100 shadow-sm">
                <div className="flex items-center gap-1.5 text-ink/80">
                  <span className="text-xs">📊</span>
                  <span className="font-semibold font-mono text-[10px]">{d.c5.rows[0].name}</span>
                </div>
                <span className="text-[10px] text-mintSuccess font-bold">{d.c5.rows[0].tag}</span>
              </div>

              <div className="flex items-center justify-between text-[11px] p-1.5 bg-white rounded-lg border border-slate-100 shadow-sm">
                <div className="flex items-center gap-1.5 text-ink/80">
                  <span className="text-xs">📑</span>
                  <span className="font-semibold font-mono text-[10px]">{d.c5.rows[1].name}</span>
                </div>
                <span className="text-[10px] text-violet font-bold">{d.c5.rows[1].tag}</span>
              </div>

              <div className="flex items-center justify-between text-[11px] p-1.5 bg-white rounded-lg border border-slate-100 shadow-sm">
                <div className="flex items-center gap-1.5 text-ink/80">
                  <span className="text-xs">🌐</span>
                  <span className="font-semibold font-mono text-[10px]">{d.c5.rows[2].name}</span>
                </div>
                <span className="text-[10px] text-coral font-bold">{d.c5.rows[2].tag}</span>
              </div>
            </div>

            <div className="pt-2 flex items-center justify-between">
              <button type="button" onClick={() => setShowSql((v) => !v)} className="text-[11px] font-bold text-violet hover:underline flex items-center gap-1">
                <span>{showSql ? 'Gizle' : "SQL'i göster"}</span>
                <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" /></svg>
              </button>
              <span className="text-[10px] text-muted">{d.c5.latency}</span>
            </div>
          </div>
        </div>

        </Node>

        {/* ================= MAIN "ZEKİ AI KARARI" CARD ================= */}
        <Node id="main" minW={520} maxW={1200} className="group/node">
        <div className="glass-card relative rounded-[28px] border-2 border-white/90 p-6 shadow-canvas-card">
        
          {/* Header badge */}
          <div className="flex items-center justify-between mb-4 pb-3 border-b border-slate-100/90">
            <div className="flex items-center gap-2.5">
              <span className="px-3 py-1 rounded-full bg-gradient-to-r from-coral to-violet text-white text-[11px] font-extrabold tracking-wide uppercase shadow-sm">
                {d.main.badge}
              </span>
              <span className="text-xs text-muted font-medium">{d.main.subject}</span>
            </div>
            <div className="flex items-center gap-2 text-xs font-semibold text-muted">
              <span className="inline-block w-2 h-2 rounded-full bg-mintSuccess animate-ping"></span>
              <span>{d.main.model}</span>
            </div>
          </div>

          <div className="flex items-start gap-6">
          
            {/* REQUIRED 160x140 area for brand-motion-slot */}
            <div id="brand-motion-slot" className="w-[160px] h-[140px] shrink-0 rounded-2xl bg-gradient-to-br from-violet/10 via-coral/10 to-amberWarn/15 border border-white flex flex-col items-center justify-center relative overflow-hidden shadow-inner group"><img src={zekiGif} alt="ZEKİ AI — Timaş Yayınları" width="960" height="600" style={{ display: 'block', width: '100%', height: '100%', objectFit: 'contain', borderRadius: 'inherit' }} /></div>

            {/* Decision Content & Recommended Actions */}
            <div className="flex-1 flex flex-col justify-between min-h-[140px]">
              <div>
                <p className="text-base font-bold text-ink leading-snug">
                  {d.main.text}
                </p>
              
                {/* Verbatim insight mention & sub-metrics */}
                <div className="mt-2.5 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-muted">
                  <span className="flex items-center gap-1">
                    <strong className="text-ink">{d.main.m1.label}</strong> {d.main.m1.value}
                  </span>
                  <span className="text-slate-300">•</span>
                  <span className="flex items-center gap-1">
                    <strong className="text-ink">{d.main.m2.label}</strong> {d.main.m2.value}
                  </span>
                  <span className="text-slate-300">•</span>
                  <span className="flex items-center gap-1">
                    <strong className="text-ink">{d.main.m3.label}</strong> {d.main.m3.value}
                  </span>
                </div>
              </div>

              {/* Action Buttons */}
              <div className="mt-4 flex items-center gap-3">
                {/* Primary Gradient Action */}
                <Link to={d.main.primaryTo} className="px-5 py-2.5 rounded-xl bg-gradient-to-r from-coral to-violet text-white text-xs font-extrabold tracking-tight shadow-md hover:shadow-lg hover:opacity-95 transition-all flex items-center gap-2 active:scale-95">
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>
                  {d.main.primary}
                </Link>

                {/* Ghost Secondary Action */}
                <Link to={d.main.secondaryTo} className="px-4 py-2.5 rounded-xl bg-slate-100 hover:bg-slate-200/80 text-ink text-xs font-bold transition-all flex items-center gap-1.5 active:scale-95">
                  <svg className="w-4 h-4 text-muted" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M4 6h16M4 12h16M4 18h7" /></svg>
                  {d.main.secondary}
                </Link>

                <div className="ml-auto text-[11px] text-muted/80 font-medium">
                  {d.main.note}
                </div>
              </div>
            </div>

          </div>
        </div>

        </Node>

        {/* ================= STICKER-LIKE BOOK COVER (Kayıp Atlas) ================= */}
        {/* Positioned pinned near the decision card with tape effect, tilted 6° */}
        <Node id="sticker" tilt={6} z={30} resizable={false} className="group hidden xl:block">
        <div>
          {/* Washi Tape Pin */}
          <div className="absolute -top-3 left-1/2 -translate-x-1/2 w-16 h-6 washi-tape rounded-sm z-40"></div>
        
          {/* Book Cover Container */}
          <div className="w-[125px] h-[175px] rounded-xl bg-gradient-to-br from-indigo-900 via-sky-700 to-teal-400 p-3 flex flex-col justify-between shadow-canvas-card border-2 border-white/80 transition-transform group-hover:scale-105 duration-200">
            <div className="flex items-center justify-between">
              <span className="text-[10px] font-black uppercase tracking-widest text-white/70">{d.sticker.kicker}</span>
              <span className="text-[10px] font-mono text-white/60">{d.sticker.meta}</span>
            </div>

            {/* Abstract Typographic Cover Art */}
            <div className="text-center my-auto">
              <div className="w-10 h-10 mx-auto rounded-full border border-white/40 flex items-center justify-center mb-1.5">
                <div className="w-6 h-6 rounded-full bg-gradient-to-tr from-amber-300 to-coral opacity-90"></div>
              </div>
              <h2 className="text-xs font-black text-white leading-tight tracking-wide drop-shadow-sm">
                {d.sticker.title}
              </h2>
              <div className="text-[10px] text-sky-100 font-medium mt-0.5">{d.sticker.sub}</div>
            </div>

            <div className="flex items-center justify-between text-[9.5px] text-white/80 border-t border-white/20 pt-1">
              <span>{d.sticker.footL}</span>
              <span className="font-bold">{d.sticker.footR}</span>
            </div>
          </div>

          {/* Small Sticker Badge */}
          <div className="absolute -bottom-2 -right-2 bg-amberWarn text-ink text-[10.5px] font-black px-2 py-0.5 rounded-full shadow-md border border-white rotate-3">
            {d.sticker.badge}
          </div>
        </div>
        </Node>

      </div>

        </div>
      </main>

      {/* ================= BOTTOM FLOATING DOCK & ZEKİ CHAT INPUT ================= */}
      <div className="absolute bottom-6 inset-x-0 flex justify-center z-40 pointer-events-none">
        <div className="glass-dock p-2.5 rounded-3xl shadow-dock-shadow flex items-center gap-3 pointer-events-auto border border-white/90 max-w-[940px] w-full">
        
          {/* 4 Quick Module Chips */}
          <div className="flex items-center gap-1.5 pl-1 shrink-0 border-r border-slate-200/80 pr-3">
            {d.dockLinks.map((c, i) => (
              <Link
                key={c.to}
                to={c.to}
                className={
                  c.active
                    ? 'px-3 py-1.5 rounded-xl bg-violet/15 text-violet text-xs font-extrabold flex items-center gap-1.5 transition hover:bg-violet/20'
                    : 'px-2.5 py-1.5 rounded-xl hover:bg-white/80 text-muted hover:text-ink text-xs font-bold transition flex items-center gap-1'
                }
              >
                {c.active && <span className="w-2 h-2 rounded-full bg-violet"></span>}
                <span>{d.dock[i]}</span>
                {!c.active && c.dot && <span className="w-1.5 h-1.5 rounded-full bg-amberWarn"></span>}
              </Link>
            ))}
          </div>

          {/* Wide Rounded AI Input */}
          <div className="flex-1 flex items-center bg-white/90 hover:bg-white rounded-2xl px-4 py-2 border border-slate-200/80 shadow-inner transition">
            <svg className="w-4 h-4 text-violet mr-2.5 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M13 10V3L4 14h7v7l9-11h-7z" /></svg>
            <input type="text" placeholder={d.askPlaceholder} value={ask} onChange={(e) => setAsk(e.target.value)} className="w-full bg-transparent text-xs font-semibold text-ink placeholder:text-muted/70 focus:outline-none" />
          </div>

          {/* Mic & Circular Gradient Send Button */}
          <div className="flex items-center gap-2 pr-1 shrink-0">

            <button onClick={onAsk} className="w-9 h-9 rounded-xl bg-gradient-to-tr from-coral to-violet text-white shadow-md hover:shadow-lg flex items-center justify-center transition-transform hover:scale-105 active:scale-95" title="Gönder">
              <svg className="w-4 h-4 transform rotate-90" fill="currentColor" viewBox="0 0 20 20"><path d="M10.894 2.553a1 1 0 00-1.788 0l-7 14a1 1 0 001.169 1.409l5-1.429A1 1 0 009 15.571V11a1 1 0 112 0v4.571a1 1 0 00.725.962l5 1.428a1 1 0 001.17-1.408l-7-14z" /></svg>
            </button>
          </div>

        </div>
      </div>

    </Shell>
  );
}
