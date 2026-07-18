import { useSearchParams } from 'react-router-dom';
import { useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { Menu, Plus } from 'lucide-react';
import { PageShell } from '@/components/PageShell';
import BiChatPanel from '@/components/BiChatPanel';
import BiChatSidebar from '@/components/bi/BiChatSidebar';
import type { BiChatResponse } from '@/api/types';
import { t } from '@/i18n';

export default function BiChatPage() {
  const qc = useQueryClient();
  const [params] = useSearchParams();
  const boardId = params.get('board') || 'default';
  const askFromUrl = params.get('ask') || undefined;
  const [sessionId, setSessionId] = useState(() => `bi-${Date.now().toString(36)}`);
  const [initialSessionId] = useState(sessionId);
  const [mobileSidebar, setMobileSidebar] = useState(false);

  const onChatResponse = (resp: BiChatResponse) => {
    if (resp.saved_query || resp.intent === 'save_query') {
      qc.invalidateQueries({ queryKey: ['bi-queries'] });
    }
    if (resp.report || resp.intent === 'report') {
      qc.invalidateQueries({ queryKey: ['bi-reports'] });
    }
    if (resp.alert || resp.intent === 'alert') {
      qc.invalidateQueries({ queryKey: ['bi-alerts'] });
    }
    if (
      resp.intent === 'dashboard' ||
      resp.intent === 'pin' ||
      resp.intent === 'pin_dashboard' ||
      resp.intent === 'analytics' ||
      resp.intent === 'superset' ||
      (resp.widgets?.length ?? 0) > 0 ||
      resp.analytics?.dashboard_id
    ) {
      void qc.invalidateQueries({ queryKey: ['bi-analytics-dashboards'] });
      void qc.invalidateQueries({ queryKey: ['bi-analytics-charts'] });
      void qc.invalidateQueries({ queryKey: ['bi-analytics-dashboard-charts'] });
    }
  };

  const newSession = () => {
    setSessionId(`bi-${Date.now().toString(36)}`);
    setMobileSidebar(false);
  };

  const selectSession = (id: string) => {
    setSessionId(id);
    setMobileSidebar(false);
  };

  return (
    <PageShell
      pageId="biChat"
      titleKey="bi.chatFullscreen"
      subtitleKey="bi.chatWelcome"
      maxWidth="max-w-[1600px]"
      showBiFlow
    >
      <div className="bi-chat-page flex min-h-0 flex-1 flex-col overflow-hidden">
        <div className="bi-chat-page-toolbar mb-2 shrink-0 lg:hidden">
          <button
            type="button"
            className="bi-chat-toolbar-btn"
            onClick={() => setMobileSidebar(true)}
          >
            <Menu className="h-5 w-5" />
            {t('bi.chatSessions')}
          </button>
          <button type="button" className="bi-chat-toolbar-btn bi-chat-toolbar-btn--primary" onClick={newSession}>
            <Plus className="h-5 w-5" />
            {t('bi.chatNewSessionShort')}
          </button>
        </div>

        <div className="bi-chat-page-grid min-h-0 flex-1">
          <BiChatSidebar
            activeId={sessionId}
            onSelect={selectSession}
            onNew={newSession}
            className="bi-chat-sidebar-rail"
            mobileOpen={mobileSidebar}
            onMobileClose={() => setMobileSidebar(false)}
          />
          <BiChatPanel
            key={sessionId}
            sessionId={sessionId}
            dashboardId={boardId}
            initialMessage={sessionId === initialSessionId ? askFromUrl : undefined}
            fullHeight
            className="bi-chat-panel-main bi-chat-panel--fullscreen-header bi-fluent-canvas"
            onResponse={onChatResponse}
          />
        </div>
      </div>
    </PageShell>
  );
}
