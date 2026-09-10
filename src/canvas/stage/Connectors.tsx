import { ACCENT_HEX, STAGE_H, STAGE_W, type CanvasCardNode } from '../types';

/** Soru balonunun sahnedeki çıkış noktası (tasarımdaki ~720,118). */
const SOURCE = { x: STAGE_W / 2, y: 124 };

/**
 * Sorudan kartlara giden kavisli bağlantılar. Tasarımdaki sabit `d` yolları
 * yerine çapa noktalarından üretilir: kart taşınınca çizgi kendi peşinden gelir.
 */
export default function Connectors({ cards }: { cards: CanvasCardNode[] }) {
  const linked = cards.filter((c) => c.connect && !c.decorative);
  if (!linked.length) return null;

  return (
    <svg
      className="pointer-events-none absolute inset-0 z-10"
      width={STAGE_W}
      height={STAGE_H}
      viewBox={`0 0 ${STAGE_W} ${STAGE_H}`}
      aria-hidden="true"
    >
      <defs>
        {linked.map((c) => {
          const hex = ACCENT_HEX[c.connect as keyof typeof ACCENT_HEX] ?? ACCENT_HEX.slate;
          return (
            <linearGradient key={c.id} id={`cv-grad-${c.id}`} x1="0%" y1="0%" x2="100%" y2="100%">
              <stop offset="0%" stopColor={hex} stopOpacity="0.6" />
              <stop offset="100%" stopColor={hex} stopOpacity="0.15" />
            </linearGradient>
          );
        })}
      </defs>
      {linked.map((c) => {
        const hex = ACCENT_HEX[c.connect as keyof typeof ACCENT_HEX] ?? ACCENT_HEX.slate;
        // Kartın üst kenarının ortası: çizginin bittiği yer.
        const tx = c.x + c.w / 2;
        const ty = c.y - 6;
        // Yatay mesafe arttıkça yay yayvanlaşsın; dikey inişte dik kalsın.
        const dx = tx - SOURCE.x;
        const spread = Math.min(Math.abs(dx) * 0.55, 240);
        const c1x = SOURCE.x + Math.sign(dx) * spread;
        const c1y = SOURCE.y - 4;
        const c2x = tx - Math.sign(dx) * Math.min(Math.abs(dx) * 0.25, 90);
        const c2y = ty - 48;
        const d = `M ${SOURCE.x.toFixed(1)} ${SOURCE.y.toFixed(1)} C ${c1x.toFixed(1)} ${c1y.toFixed(1)}, ${c2x.toFixed(
          1,
        )} ${c2y.toFixed(1)}, ${tx.toFixed(1)} ${ty.toFixed(1)}`;
        return (
          <g key={c.id}>
            <path d={d} fill="none" stroke={`url(#cv-grad-${c.id})`} strokeWidth={2} strokeLinecap="round" className="cv-flow" />
            <circle cx={tx} cy={ty} r={4} fill={hex} />
          </g>
        );
      })}
    </svg>
  );
}
