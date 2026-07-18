import type { ReactNode } from 'react';
import { useLocation } from 'react-router-dom';
import type { HelpPageId } from '@/help/pages';
import ModuleAiHero from '@/components/ModuleAiHero';
import BiFlowStepper from '@/components/bi/BiFlowStepper';
import { isModuleDashboardPage, moduleFromPageId } from '@/lib/moduleFromPageId';
import { biFlowIndexFromPath } from '@/lib/biFlow';

type PageHeaderProps = {
  pageId: HelpPageId;
  titleKey?: string;
  subtitleKey?: string;
  maxWidth?: string;
  children?: ReactNode;
  header?: ReactNode;
  heroTrailing?: ReactNode;
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
  showBiFlow = false,
  biFlowStep,
}: PageHeaderProps) {
  const { pathname, search } = useLocation();
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

  const resolvedBiStep =
    biFlowStep !== undefined ? biFlowStep : biFlowIndexFromPath(pathname, search);

  return (
    <div
      className={[
        'mobile-page ai-page-shell mx-auto flex w-full min-w-0 flex-1 flex-col animate-fade-in',
        showBiFlow ? 'gap-2 h-full min-h-0 overflow-hidden' : 'gap-2 sm:gap-3 min-h-0',
        maxWidth,
      ]
        .filter(Boolean)
        .join(' ')}
    >
      <div className={['shrink-0', showBiFlow ? 'space-y-1' : 'space-y-2'].join(' ')}>
        {header ?? defaultHeader}
        {showBiFlow && <BiFlowStepper activeIndex={resolvedBiStep} />}
      </div>
      <div
        className={[
          'ai-page-content relative z-10 flex min-h-0 min-w-0 flex-1 flex-col',
          showBiFlow ? 'gap-2 overflow-hidden' : 'gap-2 sm:gap-3 stagger-children',
        ].join(' ')}
      >
        {children}
      </div>
    </div>
  );
}
