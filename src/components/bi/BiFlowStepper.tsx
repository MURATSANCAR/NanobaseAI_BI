import { Link, useLocation } from 'react-router-dom';
import clsx from 'clsx';
import { BI_FLOW_STEPS, biFlowStepMatches } from '@/lib/biFlow';
import { t } from '@/i18n';

type BiFlowStepperProps = {
  activeIndex?: number | null;
};

function stepEmoji(key: string): string {
  const val = t(key);
  return val !== key ? val : '🔹';
}

export default function BiFlowStepper({ activeIndex = null }: BiFlowStepperProps) {
  const { pathname, search } = useLocation();
  const overview = activeIndex === null || activeIndex === undefined;

  return (
    <div className="bi-flow-stepper card overflow-x-auto p-3 [-webkit-overflow-scrolling:touch]">
      <p className="mb-2 px-1 text-[10px] font-semibold uppercase tracking-wider text-slate-400">
        {t('ux.biFlow.title')}
      </p>
      <div className="relative flex min-w-max items-center gap-1 sm:min-w-0 sm:flex-nowrap">
        {BI_FLOW_STEPS.map((step, index) => {
          const isActive = !overview && index === activeIndex;
          const isComplete = !overview && index < (activeIndex ?? 0);
          const isCurrentRoute = biFlowStepMatches(step.route, pathname, search);

          return (
            <div key={step.route} className="flex shrink-0 items-center gap-1">
              <Link
                to={step.route}
                title={t(step.labelKey)}
                className={clsx(
                  'bi-flow-step-chip group flex items-center gap-1.5 whitespace-nowrap rounded-xl px-2.5 py-2 text-xs font-semibold transition-all duration-300 sm:px-3',
                  isActive || isCurrentRoute
                    ? 'bg-sky-600 text-white shadow-md shadow-sky-200 ring-2 ring-sky-300/50'
                    : isComplete
                      ? 'bg-sky-100 text-sky-700 shadow-sm hover:bg-sky-200'
                      : 'bg-white/60 text-slate-500 hover:bg-sky-50 hover:text-sky-700',
                )}
              >
                <span className="text-sm">{stepEmoji(step.emojiKey)}</span>
                <span className="font-mono text-[10px] opacity-70">{index + 1}</span>
                <span className="hidden sm:inline">{t(step.labelKey)}</span>
              </Link>
              {index < BI_FLOW_STEPS.length - 1 && (
                <div
                  className={clsx(
                    'h-0.5 w-3 shrink-0 rounded-full sm:w-4',
                    isComplete || isActive ? 'bg-sky-400' : 'bg-slate-200',
                  )}
                  aria-hidden
                />
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
