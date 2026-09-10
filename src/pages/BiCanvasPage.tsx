import { useMemo } from 'react';
import { useParams } from 'react-router-dom';
import CanvasShell from '@/canvas/CanvasShell';
import { summarizeAlerts, summarizeSchedules, useCanvasQueries } from '@/canvas/data';
import { overviewScreen } from '@/canvas/screens/overview';
import { schedulesScreen } from '@/canvas/screens/schedules';
import { alertsScreen } from '@/canvas/screens/alerts';
import { boardsScreen } from '@/canvas/screens/boards';

/** URL parçası → ekran. Yeni modül eklemek bu haritaya bir satır eklemektir. */
const SCREENS = ['panolar', 'planli-raporlar', 'uyarilar'] as const;
type ScreenId = (typeof SCREENS)[number];

const isScreen = (v: string | undefined): v is ScreenId => SCREENS.includes((v ?? '') as ScreenId);

export default function BiCanvasPage() {
  const { screen } = useParams();
  const { config, on, schedules, alerts, analyticsStatus, dashboards } = useCanvasQueries();

  const sched = useMemo(() => summarizeSchedules(schedules.data?.schedules ?? []), [schedules.data]);
  const alert = useMemo(() => summarizeAlerts(alerts.data?.alerts ?? []), [alerts.data]);
  const boards = dashboards.data?.dashboards ?? [];
  const status = analyticsStatus.data;

  const view = useMemo(() => {
    if (!isScreen(screen)) {
      const loading = schedules.isLoading || alerts.isLoading || analyticsStatus.isLoading;
      return overviewScreen(sched, alert, status, boards.length, loading);
    }
    if (screen === 'planli-raporlar') return schedulesScreen(sched, schedules.isLoading);
    if (screen === 'uyarilar') return alertsScreen(alert, alerts.isLoading, config);
    return boardsScreen(status, boards, dashboards.isLoading);
  }, [
    screen,
    sched,
    alert,
    status,
    boards,
    config,
    schedules.isLoading,
    alerts.isLoading,
    analyticsStatus.isLoading,
    dashboards.isLoading,
  ]);

  const engineOk = on && Boolean(status?.enabled) && status?.health?.ok !== false;

  return (
    <CanvasShell
      screen={view}
      source={config.tenantId ? `${config.tenantId} · canlı` : 'portal API · canlı'}
      engineOk={engineOk}
      engineLabel={!on ? 'Bağlantı yok' : engineOk ? 'Motor bağlı' : 'Motor kapalı'}
    />
  );
}
