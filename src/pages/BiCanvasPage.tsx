import { useLayoutEffect, useMemo, useRef, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import StitchCanvas from '@/canvas/stitch/StitchCanvas';
import { alertsData, boardsData, overviewData, schedulesData } from '@/canvas/stitch/screens';
import { summarizeAlerts, summarizeSchedules, useCanvasQueries } from '@/canvas/data';
import '@/canvas/canvas.css';

/** URL parçası → ekran. Yeni modül eklemek bu haritaya bir satır eklemektir. */
const SCREENS = ['panolar', 'planli-raporlar', 'uyarilar'] as const;
type ScreenId = (typeof SCREENS)[number];
const isScreen = (v: string | undefined): v is ScreenId => SCREENS.includes((v ?? '') as ScreenId);

const STAGE_W = 1440;
const STAGE_H = 1000;
const ZOOM_MIN = 0.5;
const ZOOM_MAX = 2;

export default function BiCanvasPage() {
  const { screen } = useParams();
  const navigate = useNavigate();
  const { on, schedules, alerts, analyticsStatus, dashboards } = useCanvasQueries();

  const sched = useMemo(() => summarizeSchedules(schedules.data?.schedules ?? []), [schedules.data]);
  const alert = useMemo(() => summarizeAlerts(alerts.data?.alerts ?? []), [alerts.data]);
  const boards = dashboards.data?.dashboards ?? [];
  const status = analyticsStatus.data;
  const source = on ? 'Portal API · canlı' : 'Bağlantı yok';

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
    return () => ro.disconnect();
  }, []);

  const fit = box.w > 0 && box.h > 0 ? Math.min(box.w / STAGE_W, box.h / STAGE_H) : 1;
  const scale = fit * zoom;
  const offsetX = Math.max(0, (box.w - STAGE_W * scale) / 2);
  const offsetY = Math.max(0, (box.h - STAGE_H * scale) / 2);

  const d = useMemo(() => {
    const z = `%${Math.round(scale * 100)}`;
    if (!isScreen(screen)) {
      const loading = schedules.isLoading || alerts.isLoading || analyticsStatus.isLoading;
      return { ...overviewData(sched, alert, status, boards.length, loading, source), zoom: z };
    }
    if (screen === 'planli-raporlar') return { ...schedulesData(sched, schedules.isLoading, source), zoom: z };
    if (screen === 'uyarilar') return { ...alertsData(alert, alerts.isLoading, source), zoom: z };
    return { ...boardsData(status, boards, dashboards.isLoading, source), zoom: z };
  }, [
    screen,
    sched,
    alert,
    status,
    boards,
    source,
    scale,
    schedules.isLoading,
    alerts.isLoading,
    analyticsStatus.isLoading,
    dashboards.isLoading,
  ]);

  const ask = (q: string) => navigate(`/bi/chat?prompt=${encodeURIComponent(q)}`);
  const onZoom = (delta: number) => setZoom((z) => Math.min(ZOOM_MAX, Math.max(ZOOM_MIN, Number((z + delta).toFixed(2)))));

  return (
    // Ölçeklenen katman `absolute`: transform düzendeki yeri küçültmediği için
    // normal akışta 1440×1000 yer kaplıyor ve sağda/altta beyaz alan bırakıyordu.
    <div ref={hostRef} className="relative h-[100dvh] w-full overflow-hidden bg-[#f7fafc]">
      <div
        className="absolute left-0 top-0 origin-top-left"
        style={{
          width: STAGE_W,
          height: STAGE_H,
          transform: `translate(${offsetX}px, ${offsetY}px) scale(${scale})`,
        }}
      >
        <StitchCanvas d={d} onAsk={ask} onZoom={onZoom} />
      </div>
    </div>
  );
}
