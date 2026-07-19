import type { ReactNode } from 'react';
import type { HelpPageId } from '@/help/pages';
import ModuleAiHero from '@/components/ModuleAiHero';
import { isModuleDashboardPage, moduleFromPageId } from '@/lib/moduleFromPageId';

type PageHeaderProps = {
  pageId: HelpPageId;
  titleKey?: string;
  subtitleKey?: string;
  maxWidth?: string;
  children?: ReactNode;
  header?: ReactNode;
  heroTrailing?: ReactNode;
  /** @deprecated Setup stepper removed — kept as no-op for call-site compatibility. */
  showBiFlow?: boolean;
  biFlowStep?: number | null;
};

export function PageShell({
  pageId,
  titleKey,
  subtitleKey,
  maxWidth = 'max-w-6xl',
  header,
  heroTrailing,
  children,
}: PageHeaderProps) {
  const module = moduleFromPageId(pageId);
  const heroSize = isModuleDashboardPage(pageId) ? 'dashboard' : 'page';

  const defaultHeader =
    titleKey && subtitleKey ? (
      <ModuleAiHero
        module={module}
        size={heroSize}
        titleKey={titleKey}
        subtitleKey={subtitleKey}
        trailing={heroTrailing}
      />
    ) : null;

  return (
    <div
      className={[
        // Do not clip with overflow-hidden — Layout <main> scrolls.
        // Chat fills viewport via .ai-page-shell:has(.bi-chat-page) in CSS.
        'mobile-page ai-page-shell mx-auto flex w-full min-w-0 flex-1 flex-col gap-2 animate-fade-in sm:gap-3',
        maxWidth,
      ]
        .filter(Boolean)
        .join(' ')}
    >
      <div className="shrink-0 space-y-2">{header ?? defaultHeader}</div>
      <div className="ai-page-content relative z-10 flex min-w-0 flex-1 flex-col gap-2 sm:gap-3">
        {children}
      </div>
    </div>
  );
}
