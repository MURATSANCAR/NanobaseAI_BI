import { ArrowRight, BarChart3, Database, MessageSquare, Sparkles } from 'lucide-react';
import { Link } from 'react-router-dom';
import { useBiChatDockOptional } from '@/context/BiChatDockContext';
import { t } from '@/i18n';

const LINK_ACTIONS = [
  { to: '/bi/sources', labelKey: 'guide.bi.quickConnection', emoji: '🔌', icon: Database },
  { to: '/bi/templates', labelKey: 'guide.bi.quickTemplates', emoji: '📋', icon: Sparkles },
  { to: '/bi', labelKey: 'guide.bi.quickReports', emoji: '📈', icon: BarChart3 },
] as const;

export default function BiQuickActions() {
  const dock = useBiChatDockOptional();

  return (
    <section className="quick-actions-card bi-quick-actions">
      <h3 className="mb-3 flex items-center gap-2 text-sm font-semibold text-slate-900">
        <Sparkles className="h-4 w-4 text-sky-500" />
        {t('guide.bi.quickActionsTitle')}
      </h3>
      <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
        <button
          type="button"
          className="quick-action-link bi-quick-action-link text-left"
          onClick={() => dock?.openChat()}
        >
          <span className="text-lg">💬</span>
          <span className="text-sm font-medium">{t('guide.bi.quickChat')}</span>
          <MessageSquare className="ml-auto h-4 w-4 opacity-40" />
        </button>
        {LINK_ACTIONS.map((action) => (
          <Link key={action.to} to={action.to} className="quick-action-link bi-quick-action-link">
            <span className="text-lg">{action.emoji}</span>
            <span className="text-sm font-medium">{t(action.labelKey)}</span>
            <ArrowRight className="ml-auto h-4 w-4 opacity-40" />
          </Link>
        ))}
      </div>
    </section>
  );
}
