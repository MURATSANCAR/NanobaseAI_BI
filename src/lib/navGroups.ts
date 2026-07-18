import type { LucideIcon } from 'lucide-react';
import {
  BarChart3,
  Bell,
  BookOpen,
  CalendarClock,
  Database,
  FileBarChart,
  FileStack,
  LayoutDashboard,
  Link2,
  MessageSquare,
  Search,
  Table2,
  Wallet,
  Wrench,
} from 'lucide-react';

export type NavLinkDef = {
  to: string;
  icon: LucideIcon;
  labelKey: string;
  emojiKey: string;
  hintKey: string;
};

export type NavGroupDef = {
  titleKey: string;
  icon: LucideIcon;
  links: NavLinkDef[];
  collapsible?: boolean;
};

export const BI_NAV_GROUPS: NavGroupDef[] = [
  {
    titleKey: 'nav.group.dashboard',
    icon: LayoutDashboard,
    collapsible: false,
    links: [
      { to: '/bi', icon: BarChart3, labelKey: 'nav.bi', emojiKey: 'nav.bi.emoji', hintKey: 'nav.hint.bi' },
    ],
  },
  {
    titleKey: 'nav.group.budget',
    icon: Wallet,
    collapsible: false,
    links: [
      {
        to: '/bi/budget',
        icon: Wallet,
        labelKey: 'nav.biBudget',
        emojiKey: 'nav.biBudget.emoji',
        hintKey: 'nav.hint.biBudget',
      },
    ],
  },
  {
    titleKey: 'nav.group.ask',
    icon: MessageSquare,
    collapsible: true,
    links: [
      {
        to: '/bi/chat',
        icon: MessageSquare,
        labelKey: 'nav.biChat',
        emojiKey: 'nav.biChat.emoji',
        hintKey: 'nav.hint.biChat',
      },
      {
        to: '/bi/templates',
        icon: FileStack,
        labelKey: 'nav.biTemplates',
        emojiKey: 'nav.biTemplates.emoji',
        hintKey: 'nav.hint.biTemplates',
      },
      {
        to: '/bi/queries',
        icon: Search,
        labelKey: 'nav.biQueries',
        emojiKey: 'nav.biQueries.emoji',
        hintKey: 'nav.hint.biQueries',
      },
      {
        to: '/bi/glossary',
        icon: BookOpen,
        labelKey: 'nav.biGlossary',
        emojiKey: 'nav.biGlossary.emoji',
        hintKey: 'nav.hint.biGlossary',
      },
    ],
  },
  {
    titleKey: 'nav.group.data',
    icon: Database,
    collapsible: true,
    links: [
      {
        to: '/bi/sources',
        icon: Database,
        labelKey: 'nav.biSources',
        emojiKey: 'nav.biSources.emoji',
        hintKey: 'nav.hint.biSources',
      },
      {
        to: '/bi/schema',
        icon: Table2,
        labelKey: 'nav.biSchema',
        emojiKey: 'nav.biSchema.emoji',
        hintKey: 'nav.hint.biSchema',
      },
    ],
  },
  {
    titleKey: 'nav.group.delivery',
    icon: Link2,
    collapsible: true,
    links: [
      {
        to: '/bi/shares',
        icon: Link2,
        labelKey: 'nav.biShares',
        emojiKey: 'nav.biShares.emoji',
        hintKey: 'nav.hint.biShares',
      },
      {
        to: '/bi/schedules',
        icon: CalendarClock,
        labelKey: 'nav.biSchedules',
        emojiKey: 'nav.biSchedules.emoji',
        hintKey: 'nav.hint.biSchedules',
      },
      {
        to: '/bi/alerts',
        icon: Bell,
        labelKey: 'nav.biAlerts',
        emojiKey: 'nav.biAlerts.emoji',
        hintKey: 'nav.hint.biAlerts',
      },
      {
        to: '/bi/audit',
        icon: FileBarChart,
        labelKey: 'nav.biAudit',
        emojiKey: 'nav.biAudit.emoji',
        hintKey: 'nav.hint.biAudit',
      },
    ],
  },
  {
    titleKey: 'nav.group.settings',
    icon: Wrench,
    collapsible: true,
    links: [
      {
        to: '/bi/settings',
        icon: Wrench,
        labelKey: 'nav.biSettings',
        emojiKey: 'nav.biSettings.emoji',
        hintKey: 'nav.hint.biSettings',
      },
    ],
  },
];
