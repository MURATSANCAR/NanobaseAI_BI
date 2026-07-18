import { Link, useSearchParams } from 'react-router-dom';
import { AlertTriangle, ArrowRight } from 'lucide-react';
import { t } from '@/i18n';
import { localizeUserMessage } from '@/utils/backendLabels';
import { pipelineStepHref } from '@/lib/testPipeline';
import { isSuiteReadinessBlockedMessage } from '@/utils/suiteReadinessUi';

type Props = {
  error: Error | null | undefined;
  projectId?: string;
};

export default function ApiErrorBanner({ error, projectId: projectIdProp }: Props) {
  const [searchParams] = useSearchParams();
  const projectId = projectIdProp || searchParams.get('project_id') || '';

  if (!error) return null;

  const message = localizeUserMessage(error.message);
  const readinessBlocked = isSuiteReadinessBlockedMessage(error.message);
  const runHref = pipelineStepHref('/test/run', projectId || undefined);

  if (readinessBlocked) {
    return (
      <Link
        to={runHref}
        className="card flex items-center gap-3 border-status-fail/30 p-4 text-sm text-status-fail transition-colors hover:border-violet-300 hover:bg-violet-50/40"
      >
        <AlertTriangle className="h-4 w-4 shrink-0" />
        <span className="flex-1">
          {t('common.error')}: {message}
        </span>
        <span className="inline-flex shrink-0 items-center gap-1 text-xs font-medium text-violet-700">
          {t('qualityMap.smartSelectionGoRunPage')}
          <ArrowRight className="h-3.5 w-3.5" aria-hidden />
        </span>
      </Link>
    );
  }

  return (
    <div className="card flex items-center gap-3 border-status-fail/30 p-4 text-sm text-status-fail">
      <AlertTriangle className="h-4 w-4 shrink-0" />
      <span>
        {t('common.error')}: {message}
      </span>
    </div>
  );
}
