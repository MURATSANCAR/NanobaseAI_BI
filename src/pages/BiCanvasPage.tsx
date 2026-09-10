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

export default function BiCanvasPage() {
  const { screen } = useParams();
  const navigate = useNavigate();
  const { on, schedules, alerts, analyticsStatus, dashboards } = useCanvasQueries();

  const sched = useMemo(() => summarizeSchedules(schedules.data?.schedules ?? []), [schedules.data]);
  const alert = useMemo(() => summarizeAlerts(alerts.data?.alerts ?? []), [alerts.data]);
  const boards = dashboards.data?.dashboards ?? [];
  const status = analyticsStatus.data;
  const source = on ? 'Portal API · canlı' : 'Bağlantı yok';

  const d = useMemo(() => {
    if (!isScreen(screen)) {
      const loading = schedules.isLoading || alerts.isLoading || analyticsStatus.isLoading;
      return overviewData(sched, alert, status, boards.length, loading, source);
    }
    if (screen === 'planli-raporlar') return schedulesData(sched, schedules.isLoading, source);
    if (screen === 'uyarilar') return alertsData(alert, alerts.isLoading, source);
    return boardsData(status, boards, dashboards.isLoading, source);
  }, [
    screen,
    sched,
    alert,
    status,
    boards,
    source,
    schedules.isLoading,
    alerts.isLoading,
    analyticsStatus.isLoading,
    dashboards.isLoading,
  ]);

  // Tasarım 1440×1000 sabit çizildi. Küçük ekranda yeniden akıtmak yerine
  // sahneyi olduğu gibi ölçekliyoruz; yerleşim, eğimler ve bağlantılar bozulmaz.
  const hostRef = useRef<HTMLDivElement | null>(null);
  const [scale, setScale] = useState(1);
  useLayoutEffect(() => {
    const el = hostRef.current;
    if (!el) return;
    const fit = () => {
      const r = el.getBoundingClientRect();
      if (r.width > 0 && r.height > 0) setScale(Math.min(r.width / STAGE_W, r.height / STAGE_H));
    };
    fit();
    const ro = new ResizeObserver(fit);
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  const ask = (q: string) => navigate(`/bi/chat?prompt=${encodeURIComponent(q)}`);

  return (
    <div ref={hostRef} className="h-[100dvh] w-full overflow-hidden bg-[#f7fafc]">
      <div
        className="origin-top-left"
        style={{
          width: STAGE_W,
          height: STAGE_H,
          transform: `translate(${Math.max(0, (window.innerWidth - STAGE_W * scale) / 2)}px, 0) scale(${scale})`,
        }}
      >
        <StitchCanvas d={d} onAsk={ask} />
      </div>
    </div>
  );
}
