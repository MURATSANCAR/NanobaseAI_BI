import { useMemo, useState } from 'react';
import { useLocation } from 'react-router-dom';
import StitchCanvas from '@/canvas/stitch/StitchCanvas';
import { alertsData, boardsData, cfoData, overviewData, schedulesData } from '@/canvas/stitch/screens';
import { useCfoData } from '@/canvas/cfo';
import { ENGINE_ENABLED, EngineAuthError, ask as askEngine, type AskAnswer } from '@/canvas/engine';
import { summarizeAlerts, summarizeSchedules, useCanvasQueries } from '@/canvas/data';
import '@/canvas/canvas.css';

/** URL parçası → ekran. Yeni modül eklemek bu haritaya bir satır eklemektir. */
const SCREENS = ['panolar', 'planli-raporlar', 'uyarilar'] as const;
type ScreenId = (typeof SCREENS)[number];
const isScreen = (v: string | undefined): v is ScreenId => SCREENS.includes((v ?? '') as ScreenId);

const ZOOM_MIN = 0.5;
const ZOOM_MAX = 2;

export default function BiCanvasPage() {
  // Ekran, yolun son parçasından okunur: /timas/uyarilar → 'uyarilar'.
  const { pathname } = useLocation();
  const screen = pathname.split('/').filter(Boolean).pop();

  const { on, schedules, alerts, analyticsStatus, dashboards } = useCanvasQueries();

  const sched = useMemo(() => summarizeSchedules(schedules.data?.schedules ?? []), [schedules.data]);
  const alert = useMemo(() => summarizeAlerts(alerts.data?.alerts ?? []), [alerts.data]);
  const boards = dashboards.data?.dashboards ?? [];
  const status = analyticsStatus.data;
  const cfo = useCfoData();
  const source = ENGINE_ENABLED ? 'Logo · semantic bridge' : on ? 'Portal API · canlı' : 'Bağlantı yok';

  // Tasarım 1440×1000 sabit. Küçük ekranda yeniden akıtmak yerine sahne olduğu
  // gibi ölçekleniyor; yerleşim, eğimler ve bağlantılar bozulmuyor.
  const hostRef = useRef<HTMLDivElement | null>(null);
  const [box, setBox] = useState({ w: 0, h: 0 });
  const [zoom, setZoom] = useState(1);
  useLayoutEffect(() => {
    const el = hostRef.current;
    if (!el) return;
    const measure = () => setBox({ w: el.clientWidth, h: el.clientHeight });
    measure();
    const ro = new ResizeObserver(measure);
    ro.observe(el);
    return <StitchCanvas d={view} onAsk={ask} onZoom={onZoom} zoom={zoom} />;
}
