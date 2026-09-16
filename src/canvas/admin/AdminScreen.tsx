import { useQuery } from '@tanstack/react-query';
import { useSearchParams } from 'react-router-dom';
import { Activity, Bell, CalendarClock, History, LayoutGrid, Settings2, Users } from 'lucide-react';
import Shell from '../stitch/Shell';
import { railFor } from '../stitch/screens';
import { ENGINE_ENABLED, EngineAuthError, adminApi } from '../engine';
import NoAccess from '../NoAccess';
import Overview from './Overview';
import SettingsPanel from './SettingsPanel';
import { AlertsAdmin, CardsAdmin, ReportsAdmin } from './Definitions';
import People from './People';
import AuditLog from './AuditLog';
import { Loading, Note } from './ui';

export type AdminTab = 'overview' | 'settings' | 'reports' | 'alerts' | 'cards' | 'people' | 'audit';

const TABS: Array<{ id: AdminTab; label: string; icon: typeof Activity }> = [
  { id: 'overview', label: 'Genel durum', icon: Activity },
  { id: 'settings', label: 'Ayarlar', icon: Settings2 },
  { id: 'reports', label: 'Planlı raporlar', icon: CalendarClock },
  { id: 'alerts', label: 'Uyarılar', icon: Bell },
  { id: 'cards', label: 'Pano kartları', icon: LayoutGrid },
  { id: 'people', label: 'Kişiler', icon: Users },
  { id: 'audit', label: 'Değişiklik kaydı', icon: History },
];

export default function AdminScreen() {
  const [params, setParams] = useSearchParams();
  const tab = (TABS.find((t) => t.id === params.get('bolum'))?.id ?? 'overview') as AdminTab;
  const go = (t: AdminTab) => setParams(t === 'overview' ? {} : { bolum: t }, { replace: false });

  const me = useQuery({ queryKey: ['admin', 'me'], queryFn: adminApi.me, enabled: ENGINE_ENABLED, retry: false, staleTime: 60_000 });
  const overview = useQuery({
    queryKey: ['admin', 'overview'],
    queryFn: adminApi.overview,
    enabled: !!me.data?.isAdmin,
    retry: false,
    refetchInterval: 60_000,
  });
  const c = overview.data?.counts;
  const badge: Partial<Record<AdminTab, string>> = c
    ? { reports: String(c.reports), alerts: String(c.alerts), cards: String(c.cards), people: String(c.users) }
    : {};
  const settingsWarn = overview.data && !overview.data.email.configured;

  const body = me.isLoading ? (
    <Loading />
  ) : me.error ? (
    <Note tone="err">{me.error instanceof EngineAuthError ? 'Oturum gerekli.' : 'Yetki bilgisi okunamadı.'}</Note>
  ) : !me.data?.isAdmin ? (
    <NoAccess user={me.data?.user} />
  ) : tab === 'settings' ? (
    <SettingsPanel />
  ) : tab === 'reports' ? (
    <ReportsAdmin />
  ) : tab === 'alerts' ? (
    <AlertsAdmin />
  ) : tab === 'cards' ? (
    <CardsAdmin />
  ) : tab === 'people' ? (
    <People me={me.data.user} />
  ) : tab === 'audit' ? (
    <AuditLog />
  ) : (
    <Overview go={go} />
  );

  return (
    <Shell
      head={{
        tenant: 'Timaş Yayınları',
        section: 'Yapay Zeka Raporları',
        crumb: 'Yönetim',
        source: me.data?.user ? `${me.data.user}${me.data.isAdmin ? ' · yönetici' : ''}` : '',
        presence: overview.data ? (overview.data.email.configured ? 'E-posta hazır' : 'E-posta ayarı yok') : '',
        zoom: '%100',
      }}
      rail={railFor('/yonetim')}
    >
      <main className="absolute bottom-2 left-14 right-2 top-16 overflow-y-auto overscroll-contain sm:bottom-6 sm:left-[92px] sm:right-6 sm:top-[84px] md:overflow-visible">
        <div className="mx-auto flex w-full max-w-[1760px] flex-col gap-3 pb-4 md:h-full md:flex-row md:gap-4 md:pb-0">
          {me.data?.isAdmin && (
            <nav
              aria-label="Yönetim bölümleri"
              className="glass-panel w-full shrink-0 rounded-2xl p-2 shadow-glass-float sm:rounded-3xl md:w-[240px] md:p-3"
            >
              <div className="hidden px-2 pb-2 text-[13px] font-extrabold md:block">Yönetim</div>
              {/* Telefonda yatay kayan çipler, masaüstünde dikey liste */}
              <ul className="flex gap-1 [scrollbar-width:none] overflow-x-auto md:flex-col md:overflow-visible">
                {TABS.map((t) => {
                  const Icon = t.icon;
                  const on = t.id === tab;
                  return (
                    <li key={t.id} className="shrink-0">
                      <button
                        type="button"
                        onClick={() => go(t.id)}
                        aria-current={on ? 'page' : undefined}
                        className={[
                          'flex min-h-11 w-full items-center gap-2 whitespace-nowrap rounded-xl px-3 py-2 text-left text-[12.5px] font-semibold transition-colors sm:min-h-0',
                          on ? 'bg-white text-canvas-ink shadow-sm' : 'text-canvas-muted hover:bg-white/70 hover:text-canvas-ink',
                        ].join(' ')}
                      >
                        <Icon className={`h-4 w-4 shrink-0 ${on ? 'text-canvas-violet' : ''}`} />
                        <span className="flex-1">{t.label}</span>
                        {badge[t.id] && <span className="text-[11px] font-bold tabular-nums text-canvas-muted">{badge[t.id]}</span>}
                        {t.id === 'settings' && settingsWarn && <span className="h-2 w-2 rounded-full bg-amber-500" aria-label="E-posta ayarı eksik" />}
                      </button>
                    </li>
                  );
                })}
              </ul>
            </nav>
          )}
          <div className="glass-card min-w-0 shrink-0 rounded-2xl p-4 shadow-canvas-card sm:rounded-3xl sm:p-6 md:min-h-0 md:flex-1 md:shrink md:overflow-auto">
            <div className="mx-auto max-w-6xl">{body}</div>
          </div>
        </div>
      </main>
    </Shell>
  );
}
