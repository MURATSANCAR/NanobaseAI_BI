import { useState } from 'react';
import { Outlet, useLocation } from 'react-router-dom';
import { Menu } from 'lucide-react';
import Sidebar from './Sidebar';
import Breadcrumbs from './Breadcrumbs';
import AiAmbientShow from './AiAmbientShow';
import AuthConnectBanner from './AuthConnectBanner';
import { BiChatDockProvider } from '@/context/BiChatDockContext';
import { t } from '@/i18n';

export type LayoutOutletContext = {
  openMenu: () => void;
};

export default function Layout() {
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const location = useLocation();

  const path = location.pathname;
  const isBiCanvas = path === '/bi' || path === '/bi/';
  const isBiChat = path.startsWith('/bi/chat');
  const isBiImmersive = isBiCanvas || isBiChat;

  const outletContext: LayoutOutletContext = {
    openMenu: () => setSidebarOpen(true),
  };

  return (
    <BiChatDockProvider>
      <div className="relative h-[100dvh] min-h-0 overflow-hidden bg-gradient-to-br from-violet-100 via-white to-sky-100 text-slate-800">
        <AiAmbientShow variant="bi" intensity={isBiCanvas ? 'subtle' : 'full'} />

        <div
          className={[
            'relative z-10 flex h-full min-h-0',
            isBiCanvas
              ? 'p-0 pb-[env(safe-area-inset-bottom)] sm:p-1.5 sm:pb-[max(0.375rem,env(safe-area-inset-bottom))] lg:p-3'
              : 'p-1.5 pb-[max(0.375rem,env(safe-area-inset-bottom))] sm:p-2.5 lg:p-3',
          ].join(' ')}
        >
          <Sidebar open={sidebarOpen} onClose={() => setSidebarOpen(false)} />

          <div
            className={[
              'ai-module-shell relative flex min-h-0 min-w-0 flex-1 flex-col border border-white/80 bg-gradient-to-br from-sky-50/30 via-white/40 to-indigo-50/30 shadow-2xl backdrop-blur-xl',
              isBiCanvas ? 'rounded-none sm:rounded-2xl lg:rounded-3xl' : 'rounded-2xl sm:rounded-3xl',
            ].join(' ')}
          >
            {!isBiCanvas && (
              <button
                type="button"
                className="absolute left-3 top-3 z-30 rounded-2xl border border-white/70 bg-white/80 p-2 text-slate-600 shadow-sm backdrop-blur transition hover:bg-white lg:hidden"
                onClick={() => setSidebarOpen(true)}
                aria-label={t('nav.openMenu')}
              >
                <Menu className="h-5 w-5" />
              </button>
            )}

            <AuthConnectBanner />
            <main
              className={[
                'relative flex min-h-0 flex-1 flex-col overflow-x-hidden',
                isBiImmersive ? 'overflow-hidden' : 'overflow-y-auto',
                isBiCanvas ? 'p-0' : isBiChat ? 'p-1.5 sm:p-2' : 'p-2 pt-12 sm:p-4 sm:pt-4 lg:p-5 lg:pt-5',
              ].join(' ')}
            >
              {!isBiImmersive && (
                <div className="shrink-0">
                  <Breadcrumbs />
                </div>
              )}
              <div
                className={
                  isBiImmersive
                    ? 'flex min-h-0 flex-1 flex-col overflow-hidden'
                    : 'flex min-h-0 min-w-0 flex-1 flex-col'
                }
              >
                <Outlet context={outletContext} />
              </div>
            </main>
          </div>
        </div>
      </div>
    </BiChatDockProvider>
  );
}
