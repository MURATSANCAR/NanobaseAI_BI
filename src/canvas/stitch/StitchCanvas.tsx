import { useState } from 'react';
import { Link } from 'react-router-dom';
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
const RAIL_ICONS = [
  (
    <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z" /></svg>
  ),
  (
    <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M13 7h8m0 0v8m0-8l-8 8-4-4-6 6" /></svg>
  ),
  (
    <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10" /></svg>
  ),
  (
    <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" /></svg>
  ),
  (
    <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" /></svg>
  ),
  (
    <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" /></svg>
  ),
  (
    <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M7 12l3-3 3 3 4-4M8 21l4-4 4 4M3 4h18M4 4h16v12a1 1 0 01-1 1H5a1 1 0 01-1-1V4z" /></svg>
  ),
  (
    <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" /></svg>
  ),
  (
    <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.247 18 16.5 18c-1.746 0-3.332.477-4.5 1.253" /></svg>
  ),
  (
    <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M15 17h5l-1.405-1.405A2.032 2.032 0 0118 14.158V11a6.002 6.002 0 00-4-5.659V5a2 2 0 10-4 0v.341C7.67 6.165 6 8.388 6 11v3.159c0 .538-.214 1.055-.595 1.436L4 17h5m6 0v1a3 3 0 11-6 0v-1m6 0H9" /></svg>
  ),
];

export default function StitchCanvas({
  d,
  onAsk: onSubmitAsk,
  onZoom,
}: {
  d: StitchCanvasData;
  onAsk?: (q: string) => void;
  onZoom?: (delta: number) => void;
}) {
  const [ask, setAsk] = useState('');
  const onAsk = () => {
    const q = ask.trim();
    if (q) onSubmitAsk?.(q);
  };
  return (
    <div className="bg-mesh-canvas font-canvas text-ink w-[1440px] h-[1000px] overflow-hidden select-none relative">

    {/* Interactive Dot Grid Overlay */}
    <div className="absolute inset-0 dot-grid pointer-events-none z-0"></div>

    {/* ================= TOP FLOATING NAVIGATION ================= */}
    <header className="absolute top-5 inset-x-7 flex items-center justify-between z-40 pointer-events-none">
      {/* Top-Left Glass Breadcrumb Pill */}
      <div className="glass-panel px-4 py-2 rounded-full shadow-glass-float flex items-center gap-3 pointer-events-auto transition-transform hover:scale-[1.01]">
        <div className="w-7 h-7 rounded-full bg-gradient-to-tr from-coral to-violet flex items-center justify-center text-white font-black text-xs shadow-sm">
          T
        </div>
        <div className="flex items-center text-xs font-semibold tracking-tight text-ink">
          <span className="text-ink font-bold hover:text-violet cursor-pointer transition">{d.tenant}</span>
          <svg className="w-3.5 h-3.5 mx-1.5 text-muted/60" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M9 5l7 7-7 7" /></svg>
          <span className="text-muted hover:text-ink cursor-pointer transition">{d.section}</span>
          <svg className="w-3.5 h-3.5 mx-1.5 text-muted/60" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M9 5l7 7-7 7" /></svg>
          <span className="bg-violet/10 text-violet px-2 py-0.5 rounded-full font-bold flex items-center gap-1.5">
            <span className="w-1.5 h-1.5 rounded-full bg-violet animate-pulse"></span>
            {d.crumb}
          </span>
        </div>
        <span className="text-[10px] text-muted/70 border-l border-slate-200/80 pl-2.5 font-medium">{d.source}</span>
      </div>

      {/* Top-Right Actions & Collaboration Pill */}
      <div className="flex items-center gap-3 pointer-events-auto">
        {/* Collaboration Avatars */}
        <div className="glass-panel px-3 py-1.5 rounded-full shadow-glass-float flex items-center gap-2">
          <div className="flex -space-x-1.5 items-center">
            <div className="w-7 h-7 rounded-full bg-gradient-to-br from-amber-400 to-orange-500 text-white font-bold text-[11px] flex items-center justify-center ring-2 ring-white shadow-sm" title="Emre Berk (Genel Yayın Yönetmeni)">EB</div>
            <div className="w-7 h-7 rounded-full bg-gradient-to-br from-purple-500 to-indigo-600 text-white font-bold text-[11px] flex items-center justify-center ring-2 ring-white shadow-sm" title="Elif Aydın (Yazar & Danışman)">EA</div>
            <div className="w-7 h-7 rounded-full bg-gradient-to-br from-emerald-400 to-teal-600 text-white font-bold text-[11px] flex items-center justify-center ring-2 ring-white shadow-sm" title="Selin Kara (Üretim & Telif)">SK</div>
          </div>
          <span className="text-[11px] font-semibold text-muted pl-1">{d.presence}</span>
        </div>

        {/* Share Button */}
        <button className="glass-panel px-4 py-2 rounded-full shadow-glass-float flex items-center gap-1.5 text-xs font-bold text-ink hover:bg-white hover:text-violet transition-all group">
          <svg className="w-3.5 h-3.5 text-muted group-hover:text-violet transition" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M8.684 13.342C8.886 12.938 9 12.482 9 12c0-.482-.114-.938-.316-1.342m0 2.684a3 3 0 110-2.684m0 2.684l6.632 3.316m-6.632-6l6.632-3.316m0 0a3 3 0 105.367-2.684 3 3 0 00-5.367 2.684zm0 9.316a3 3 0 105.368 2.684 3 3 0 00-5.368-2.684z" /></svg>
          Paylaş
        </button>

        {/* Canvas Zoom Indicator & Controls */}
        <div className="glass-panel px-3 py-1.5 rounded-full shadow-glass-float flex items-center gap-2 text-xs font-semibold text-ink">
          <button type="button" aria-label="Uzaklaştır" onClick={() => onZoom?.(-0.1)} className="w-5 h-5 flex items-center justify-center rounded-full hover:bg-slate-100 text-muted font-bold">-</button>
          <span className="text-xs font-bold w-9 text-center text-ink">{d.zoom}</span>
          <button type="button" aria-label="Yakınlaştır" onClick={() => onZoom?.(0.1)} className="w-5 h-5 flex items-center justify-center rounded-full hover:bg-slate-100 text-muted font-bold">+</button>
        </div>
      </div>
    </header>

    {/* ================= LEFT FLOATING VERTICAL MODULE RAIL ================= */}
      {/* Ray yalnız var olan ekranları taşır; ölü bağlantı yok. */}
      <aside className="absolute left-6 top-24 bottom-24 z-30 flex flex-col items-center justify-start gap-2.5 py-4 px-2 w-[54px] glass-panel rounded-3xl shadow-glass-float">
        {d.rail.map((item, i) => (
          <div key={item.to} className="relative group flex items-center">
            <Link
              to={item.to}
              aria-label={item.label}
              className={
                item.badge === 'Aktif'
                  ? 'w-10 h-10 rounded-2xl bg-gradient-to-tr from-coral to-violet text-white shadow-md flex items-center justify-center transition-transform hover:scale-105'
                  : 'w-10 h-10 rounded-2xl hover:bg-white/80 text-muted hover:text-ink transition flex items-center justify-center'
              }
            >
              {RAIL_ICONS[i % RAIL_ICONS.length]}
            </Link>
            <div
              className={
                item.badge === 'Aktif'
                  ? 'absolute left-14 bg-slate-900 text-white text-[11px] font-bold px-2.5 py-1 rounded-lg shadow-xl whitespace-nowrap z-50 flex items-center gap-1.5'
                  : 'absolute left-14 bg-slate-900 text-white text-[11px] font-semibold px-2.5 py-1 rounded-lg shadow-xl whitespace-nowrap opacity-0 group-hover:opacity-100 pointer-events-none transition duration-150'
              }
            >
              <span>{item.label}</span>
              {item.badge === 'Aktif' && (
                <span className="bg-violet-500 text-white text-[9px] px-1.5 py-0.2 rounded font-bold">Aktif</span>
              )}
            </div>
          </div>
        ))}
      </aside>

      {/* ================= INFINITE CANVAS STAGE ================= */}
    <main className="w-full h-full relative overflow-hidden">
    
      {/* SVG CURVED CONNECTOR LINES (Mind-map Constellation) */}
      <svg className="absolute inset-0 w-full h-full pointer-events-none z-10" xmlns="http://www.w3.org/2000/svg">
        <defs>
          {/* Gradients for connectors */}
          <linearGradient id="grad-c1" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stopColor="#FF6B4A" stopOpacity="0.6" />
            <stop offset="100%" stopColor="#FF6B4A" stopOpacity="0.15" />
          </linearGradient>
          <linearGradient id="grad-c2" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stopColor="#7C5CFF" stopOpacity="0.6" />
            <stop offset="100%" stopColor="#7C5CFF" stopOpacity="0.15" />
          </linearGradient>
          <linearGradient id="grad-c3" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stopColor="#10B981" stopOpacity="0.6" />
            <stop offset="100%" stopColor="#10B981" stopOpacity="0.15" />
          </linearGradient>
          <linearGradient id="grad-c4" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stopColor="#F59E0B" stopOpacity="0.6" />
            <stop offset="100%" stopColor="#F59E0B" stopOpacity="0.15" />
          </linearGradient>
          <linearGradient id="grad-c5" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stopColor="#6B7280" stopOpacity="0.5" />
            <stop offset="100%" stopColor="#6B7280" stopOpacity="0.15" />
          </linearGradient>
          {/* Marker Dots */}
          <marker id="dot-coral" viewBox="0 0 10 10" refX="5" refY="5" markerWidth="6" markerHeight="6">
            <circle cx="5" cy="5" r="3.5" fill="#FF6B4A" />
          </marker>
          <marker id="dot-violet" viewBox="0 0 10 10" refX="5" refY="5" markerWidth="6" markerHeight="6">
            <circle cx="5" cy="5" r="3.5" fill="#7C5CFF" />
          </marker>
        </defs>

        {/* Center question anchor: ~ (720, 118) */}
        {/* Line to 1. Stok (approx 215, 205) */}
        <path d="M 640 115 C 440 115, 300 145, 235 200" fill="none" stroke="url(#grad-c1)" strokeWidth="2" strokeLinecap="round" className="flowing-line" />
        <circle cx="235" cy="200" r="4" fill="#FF6B4A" />

        {/* Line to 2. Talep Tahmini (approx 475, 210) */}
        <path d="M 690 120 C 580 150, 520 160, 480 205" fill="none" stroke="url(#grad-c2)" strokeWidth="2" strokeLinecap="round" className="flowing-line" />
        <circle cx="480" cy="205" r="4" fill="#7C5CFF" />

        {/* Line to 3. Kanal Dağılımı (approx 720, 220) */}
        <path d="M 720 124 C 720 160, 725 170, 725 210" fill="none" stroke="url(#grad-c3)" strokeWidth="2" strokeLinecap="round" className="flowing-line" />
        <circle cx="725" cy="210" r="4" fill="#10B981" />

        {/* Line to 4. Telif Etkisi (approx 965, 210) */}
        <path d="M 750 120 C 860 150, 920 160, 960 205" fill="none" stroke="url(#grad-c4)" strokeWidth="2" strokeLinecap="round" className="flowing-line" />
        <circle cx="960" cy="205" r="4" fill="#F59E0B" />

        {/* Line to 5. Kanıt (approx 1220, 200) */}
        <path d="M 800 115 C 1000 115, 1140 145, 1205 200" fill="none" stroke="url(#grad-c5)" strokeWidth="2" strokeLinecap="round" className="flowing-line" />
        <circle cx="1205" cy="200" r="4" fill="#6B7280" />

        {/* Secondary Connectors to ZEKİ Karar Card at bottom */}
        <path d="M 330 380 C 420 440, 490 450, 530 470" fill="none" stroke="rgba(255, 107, 74, 0.25)" strokeWidth="1.5" strokeDasharray="4 4" />
        <path d="M 580 405 C 600 435, 620 450, 640 470" fill="none" stroke="rgba(124, 92, 255, 0.25)" strokeWidth="1.5" strokeDasharray="4 4" />
        <path d="M 940 380 C 900 430, 850 455, 820 470" fill="none" stroke="rgba(245, 158, 11, 0.25)" strokeWidth="1.5" strokeDasharray="4 4" />
      
        {/* Ghost connector to previous cluster */}
        <path d="M 1320 280 C 1370 300, 1400 320, 1425 330" fill="none" stroke="rgba(107, 114, 128, 0.2)" strokeWidth="1.5" strokeDasharray="4 4" />
      </svg>

      {/* ================= CENTER CONSTELLATION CONTAINER ================= */}
      <div className="relative w-full h-full max-w-[1440px] mx-auto pt-16">
      
        {/* USER'S QUESTION BUBBLE (Center Top Anchor) */}
        <div className="absolute left-1/2 -translate-x-1/2 top-16 z-30 animate-float-slow">
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
        <div className="absolute left-[110px] top-[175px] w-[235px] glass-card rounded-[24px] p-4 shadow-canvas-card z-20" style={{transform: 'rotate(-3deg)'}}>
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

        {/* CARD 2: Talep Tahmini (Rotated +2°) */}
        <div className="absolute left-[365px] top-[170px] w-[250px] glass-card rounded-[24px] p-4 shadow-canvas-card z-20" style={{transform: 'rotate(2deg)'}}>
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
                <path d={d.c2.areaPath} fill="url(#areaGrad)" />
                <path d={d.c2.linePath} fill="none" stroke="#7C5CFF" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" />
                {/* Highlight dot */}
                <circle cx={d.c2.dot[0]} cy={d.c2.dot[1]} r="3.5" fill="#7C5CFF" stroke="#FFFFFF" strokeWidth="2" />
              </svg>
              <div className="flex justify-between text-[9px] text-muted font-semibold mt-1">
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

        {/* CARD 3: Kanal Dağılımı (Rotated -1.5°) */}
        <div className="absolute left-[635px] top-[185px] w-[240px] glass-card rounded-[24px] p-4 shadow-canvas-card z-20" style={{transform: 'rotate(-1.5deg)'}}>
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

        {/* CARD 4: Telif Etkisi (Rotated +1°) */}
        <div className="absolute left-[895px] top-[170px] w-[235px] glass-card rounded-[24px] p-4 shadow-canvas-card z-20" style={{transform: 'rotate(1deg)'}}>
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

        {/* CARD 5: Kanıt / Veri Dayanağı (Rotated +2.5°) */}
        <div className="absolute left-[1150px] top-[175px] w-[215px] glass-card rounded-[24px] p-4 shadow-canvas-card z-20" style={{transform: 'rotate(2.5deg)'}}>
          <div className="flex items-center justify-between pb-2 border-b border-slate-100">
            <div className="flex items-center gap-2">
              <span className="w-6 h-6 rounded-lg bg-slate-100 text-slate-700 flex items-center justify-center text-xs font-bold">🔍</span>
              <span className="text-xs font-extrabold tracking-tight text-ink">{d.c5.title}</span>
            </div>
            {/* Tiny Sample Data Chip Inside Kanıt Card as requested */}
            <span className="text-[9px] font-bold px-1.5 py-0.5 rounded bg-slate-100 text-muted border border-slate-200">{d.c5.badge}</span>
          </div>

          <div className="mt-3 space-y-2">
            <div className="text-xs font-bold text-ink">
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
              <a href="#" className="text-[11px] font-bold text-violet hover:underline flex items-center gap-1">
                <span>SQL'i göster</span>
                <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" /></svg>
              </a>
              <span className="text-[10px] text-muted">{d.c5.latency}</span>
            </div>
          </div>
        </div>

        {/* ================= MAIN "ZEKİ AI KARARI" CARD ================= */}
        <div className="absolute left-1/2 -translate-x-1/2 top-[445px] w-[860px] glass-card rounded-[28px] p-6 shadow-canvas-card border-2 border-white/90 z-20">
        
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

        {/* ================= STICKER-LIKE BOOK COVER (Kayıp Atlas) ================= */}
        {/* Positioned pinned near the decision card with tape effect, tilted 6° */}
        <div className="absolute left-[1185px] top-[445px] z-30 group" style={{transform: 'rotate(6deg)'}}>
          {/* Washi Tape Pin */}
          <div className="absolute -top-3 left-1/2 -translate-x-1/2 w-16 h-6 washi-tape rounded-sm z-40"></div>
        
          {/* Book Cover Container */}
          <div className="w-[125px] h-[175px] rounded-xl bg-gradient-to-br from-indigo-900 via-sky-700 to-teal-400 p-3 flex flex-col justify-between shadow-canvas-card border-2 border-white/80 transition-transform group-hover:scale-105 duration-200">
            <div className="flex items-center justify-between">
              <span className="text-[8px] font-black uppercase tracking-widest text-white/70">{d.sticker.kicker}</span>
              <span className="text-[8px] font-mono text-white/60">{d.sticker.meta}</span>
            </div>

            {/* Abstract Typographic Cover Art */}
            <div className="text-center my-auto">
              <div className="w-10 h-10 mx-auto rounded-full border border-white/40 flex items-center justify-center mb-1.5">
                <div className="w-6 h-6 rounded-full bg-gradient-to-tr from-amber-300 to-coral opacity-90"></div>
              </div>
              <h2 className="text-xs font-black text-white leading-tight tracking-wide drop-shadow-sm">
                {d.sticker.title}
              </h2>
              <div className="text-[8px] text-sky-100 font-medium mt-0.5">{d.sticker.sub}</div>
            </div>

            <div className="flex items-center justify-between text-[7px] text-white/80 border-t border-white/20 pt-1">
              <span>{d.sticker.footL}</span>
              <span className="font-bold">{d.sticker.footR}</span>
            </div>
          </div>

          {/* Small Sticker Badge */}
          <div className="absolute -bottom-2 -right-2 bg-amberWarn text-ink text-[9px] font-black px-2 py-0.5 rounded-full shadow-md border border-white rotate-3">
            {d.sticker.badge}
          </div>
        </div>

        {/* ================= FAINT EARLIER ANSWER CLUSTER (Infinite Canvas Feel) ================= */}
        <div className="absolute left-[1340px] top-[240px] opacity-40 pointer-events-none filter blur-[0.5px] z-10" style={{transform: 'rotate(-3deg)'}}>
          <div className="glass-card w-[220px] rounded-[24px] p-4 shadow-md border border-slate-300">
            <div className="flex items-center justify-between pb-2 border-b border-slate-200">
              <span className="text-[11px] font-extrabold text-slate-700">{d.ghost.title}</span>
              <span className="text-[9px] font-bold text-amberWarn bg-amber-50 px-1.5 py-0.5 rounded">{d.ghost.badge}</span>
            </div>
            <p className="text-[10px] text-slate-600 mt-2 font-medium leading-relaxed">
              {d.ghost.text}
            </p>
            <div className="mt-2 text-[9px] text-slate-400">
              {d.ghost.foot}
            </div>
          </div>
        </div>

      </div>

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
            <button className="w-9 h-9 rounded-xl hover:bg-white/90 text-muted hover:text-ink flex items-center justify-center transition" title="Sesli Soru">
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4m-4-8a3 3 0 01-3-3V5a3 3 0 116 0v6a3 3 0 01-3 3z" /></svg>
            </button>

            <button onClick={onAsk} className="w-9 h-9 rounded-xl bg-gradient-to-tr from-coral to-violet text-white shadow-md hover:shadow-lg flex items-center justify-center transition-transform hover:scale-105 active:scale-95" title="Gönder">
              <svg className="w-4 h-4 transform rotate-90" fill="currentColor" viewBox="0 0 20 20"><path d="M10.894 2.553a1 1 0 00-1.788 0l-7 14a1 1 0 001.169 1.409l5-1.429A1 1 0 009 15.571V11a1 1 0 112 0v4.571a1 1 0 00.725.962l5 1.428a1 1 0 001.17-1.408l-7-14z" /></svg>
            </button>
          </div>

        </div>
      </div>

      </main>
    </div>
  );
}
