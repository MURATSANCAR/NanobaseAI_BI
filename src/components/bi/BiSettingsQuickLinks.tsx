import { Link } from 'react-router-dom';
import {
  BookOpen,
  CalendarClock,
  Database,
  Link2,
  Plug,
  ScrollText,
  Siren,
} from 'lucide-react';
import { t } from '@/i18n';

const LINKS = [
  { to: '/bi/sources', key: 'bi.settings.link.sources', Icon: Plug },
  { to: '/bi/schema', key: 'bi.settings.link.schema', Icon: Database },
  { to: '/bi/glossary', key: 'bi.settings.link.glossary', Icon: BookOpen },
  { to: '/bi/alerts', key: 'bi.settings.link.alerts', Icon: Siren },
  { to: '/bi/shares', key: 'bi.settings.link.shares', Icon: Link2 },
  { to: '/bi/schedules', key: 'bi.settings.link.schedules', Icon: CalendarClock },
  { to: '/bi/audit', key: 'bi.settings.link.audit', Icon: ScrollText },
] as const;

export default function BiSettingsQuickLinks() {
  return (
    <section className="card space-y-3 p-4" data-testid="bi-settings-quick-links">
      <div>
        <h3 className="text-sm font-semibold text-slate-900">{t('bi.settings.quickLinksTitle')}</h3>
        <p className="mt-0.5 text-xs text-slate-500">{t('bi.settings.quickLinksHint')}</p>
      </div>
      <ul className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
        {LINKS.map(({ to, key, Icon }) => (
          <li key={to}>
            <Link
              to={to}
              className="flex items-center gap-2 rounded-xl border border-slate-200 bg-slate-50/80 px-3 py-2.5 text-sm font-medium text-slate-800 transition hover:border-violet-300 hover:bg-violet-50 hover:text-violet-900"
            >
              <Icon className="h-4 w-4 text-violet-600" />
              {t(key)}
            </Link>
          </li>
        ))}
      </ul>
    </section>
  );
}
