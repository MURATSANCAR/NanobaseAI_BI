import { useMemo, useState } from 'react';
import { NavLink, useNavigate } from 'react-router-dom';
import CanvasStage, { STACK_BREAKPOINT, type StageView } from './stage/CanvasStage';
import Connectors from './stage/Connectors';
import CanvasRail from './shell/CanvasRail';
import { CanvasDock, CanvasMinimap, CanvasTopBar, QuestionBubble } from './shell/CanvasChrome';
import { ACCENT_HEX, type CanvasScreen } from './types';
import './canvas.css';

const DOCK_LINKS = [
  { to: '/bi/canvas', label: 'Genel bakış' },
  { to: '/bi/canvas/panolar', label: 'Panolar' },
  { to: '/bi/canvas/planli-raporlar', label: 'Planlı raporlar' },
  { to: '/bi/canvas/uyarilar', label: 'Uyarılar' },
];

type Props = {
  screen: CanvasScreen;
  source: string;
  engineOk: boolean;
  engineLabel: string;
};

/**
 * Kanvasın kabuğu: ray, üst şerit, sahne, dock ve tuval haritası.
 * Ekranlar yalnız `CanvasScreen` verisi üretir; yerleşim burada çizilir.
 */
export default function CanvasShell({ screen, source, engineOk, engineLabel }: Props) {
  const [zoom, setZoom] = useState(1);
  const [view, setView] = useState<StageView | null>(null);
  const [ask, setAsk] = useState('');
  const navigate = useNavigate();
  const stacked = view?.stacked ?? false;

  const ordered = useMemo(
    () => [...screen.cards].sort((a, b) => (a.order ?? a.y) - (b.order ?? b.y) || a.x - b.x),
    [screen.cards],
  );

  const submitAsk = () => {
    const q = ask.trim();
    if (!q) return;
    navigate(`/bi/chat?prompt=${encodeURIComponent(q)}`);
  };

  return (
    <div className="cv-mesh relative h-[100dvh] w-full overflow-hidden font-canvas text-canvas-ink">
      <div className="cv-dots pointer-events-none absolute inset-0 z-0" />

      <CanvasTopBar
        crumb={screen.crumb}
        source={source}
        engineOk={engineOk}
        engineLabel={engineLabel}
        zoom={zoom}
        onZoom={setZoom}
        stacked={stacked}
      />

      {!stacked && <CanvasRail />}

      <main
        className={[
          'absolute bottom-24 top-24 z-20',
          stacked ? 'left-0 right-0' : 'left-[92px] right-7',
        ].join(' ')}
      >
        <CanvasStage
          zoom={zoom}
          onZoomChange={setZoom}
          onView={setView}
          underlay={<Connectors cards={screen.cards} />}
        >
          {stacked ? (
            <>
              <QuestionBubble q={screen.question} stacked />
              {ordered
                .filter((c) => !c.decorative)
                .map((c) => (
                  <div key={c.id}>{c.render({ stacked: true })}</div>
                ))}
            </>
          ) : (
            <>
              <QuestionBubble q={screen.question} />
              {screen.cards.map((c) => (
                <div
                  key={c.id}
                  className="absolute"
                  style={{
                    left: c.x,
                    top: c.y,
                    width: c.w,
                    zIndex: c.z ?? 20,
                    transform: c.rot ? `rotate(${c.rot}deg)` : undefined,
                  }}
                >
                  {c.render({ stacked: false })}
                </div>
              ))}
            </>
          )}
        </CanvasStage>
      </main>

      <CanvasDock
        placeholder={screen.askPlaceholder ?? 'ZEKİ’ye sor…'}
        value={ask}
        onChange={setAsk}
        onSubmit={submitAsk}
        chips={DOCK_LINKS.map((l) => (
          <NavLink
            key={l.to}
            to={l.to}
            end={l.to === '/bi/canvas'}
            className={({ isActive }) =>
              [
                'flex items-center gap-1.5 rounded-xl px-2.5 py-1.5 text-xs font-bold transition',
                isActive ? 'bg-canvas-violet/15 text-canvas-violet' : 'text-canvas-muted hover:bg-white/80 hover:text-canvas-ink',
              ].join(' ')
            }
          >
            {l.label}
          </NavLink>
        ))}
      />

      {!stacked && (
        <CanvasMinimap
          zoom={zoom}
          dots={screen.cards.map((c) => ({
            id: c.id,
            x: c.x,
            y: c.y,
            w: c.w,
            accent: ACCENT_HEX[c.connect ? c.connect : 'slate'],
          }))}
        />
      )}
    </div>
  );
}

export { STACK_BREAKPOINT };
