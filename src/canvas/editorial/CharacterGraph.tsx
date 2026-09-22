/** Kitap karakter ağı: düğüm = karakter (boyut = olay sayısı), kenar = ortak olay (kalınlık).
 *  Graf aracının (event_triples/synergies) çıktısıyla beslenir. Deterministik yerleşim: en çok
 *  olaya sahip karakter merkezde, kalanlar olaya göre halkada — fizik simülasyonu yok, her açılışta
 *  aynı görünür. Salt görsel; okunur metin cevabın kendisinde kalır. */

export type GraphNode = { name: string; count: number; role?: 'lead' | 'family' | 'other' };
export type GraphEdge = { a: string; b: string; weight: number };

const W = 680;
const H = 430;
const CX = W / 2;
const CY = 200;
const RING = 150;
const MAX_NODES = 9;

const FILL: Record<NonNullable<GraphNode['role']>, string> = {
  lead: '#7c5cff',
  family: '#a78bfa',
  other: '#c4b5fd',
};

export default function CharacterGraph({ nodes, edges }: { nodes: GraphNode[]; edges: GraphEdge[] }) {
  const top = [...nodes].sort((a, b) => b.count - a.count).slice(0, MAX_NODES);
  if (top.length < 2) return null;
  const maxCount = top[0].count || 1;
  const shown = new Set(top.map((n) => n.name));
  const links = edges.filter((e) => shown.has(e.a) && shown.has(e.b) && e.a !== e.b);
  const maxW = links.reduce((m, e) => Math.max(m, e.weight), 1);

  const pos = new Map<string, { x: number; y: number; r: number; role: GraphNode['role'] }>();
  top.forEach((n, i) => {
    const r = 9 + 25 * Math.sqrt(n.count / maxCount);
    if (i === 0) {
      pos.set(n.name, { x: CX, y: CY, r, role: n.role ?? 'lead' });
    } else {
      const a = -Math.PI / 2 + ((i - 1) * 2 * Math.PI) / (top.length - 1);
      pos.set(n.name, { x: CX + RING * Math.cos(a), y: CY + RING * Math.sin(a), r, role: n.role ?? 'other' });
    }
  });

  return (
    <figure className="zk-graph my-1 w-full">
      <svg viewBox={`0 0 ${W} ${H}`} width="100%" role="img" aria-labelledby="zk-graph-title" className="overflow-visible">
        <title id="zk-graph-title">Kitap karakter ağı</title>
        <desc>Karakterler düğüm (boyut = olay sayısı), çizgiler ortak olayları gösterir.</desc>
        <g stroke="#7c5cff" fill="none">
          {links.map((e, i) => {
            const p = pos.get(e.a)!;
            const q = pos.get(e.b)!;
            return (
              <line key={i} x1={p.x} y1={p.y} x2={q.x} y2={q.y}
                strokeWidth={1 + (e.weight / maxW) * 4}
                strokeOpacity={0.18 + 0.32 * (e.weight / maxW)} strokeLinecap="round" />
            );
          })}
        </g>
        {top.map((n) => {
          const p = pos.get(n.name)!;
          const below = p.y > CY + 20;
          return (
            <g key={n.name}>
              <circle cx={p.x} cy={p.y} r={p.r} fill={FILL[p.role ?? 'other']} />
              <text x={p.x} y={below ? p.y + p.r + 15 : p.y - p.r - 7}
                textAnchor="middle" className="fill-canvas-ink text-[12.5px] font-semibold">
                {n.name}
              </text>
              <text x={p.x} y={below ? p.y + p.r + 29 : p.y - p.r - 21}
                textAnchor="middle" className="fill-canvas-muted text-[11px]">
                {n.count} olay
              </text>
            </g>
          );
        })}
      </svg>
      <figcaption className="mt-1 flex flex-wrap items-center gap-x-4 gap-y-1 px-1 text-[11px] text-canvas-muted">
        <span className="flex items-center gap-1.5"><span className="h-2.5 w-2.5 rounded-full" style={{ background: FILL.lead }} />başkarakter</span>
        <span className="flex items-center gap-1.5"><span className="h-2.5 w-2.5 rounded-full" style={{ background: FILL.family }} />yakın</span>
        <span>çizgi kalınlığı = ortak olay</span>
      </figcaption>
    </figure>
  );
}
