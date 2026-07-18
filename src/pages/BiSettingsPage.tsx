import BiBindingStewardPanel from '@/components/bi/BiBindingStewardPanel';
import BiBrandingSettingsForm from '@/components/bi/BiBrandingSettingsForm';
import BiOpsHealthPanel from '@/components/bi/BiOpsHealthPanel';
import BiSemanticStewardPanel from '@/components/bi/BiSemanticStewardPanel';
import BiSensitivityPanel from '@/components/bi/BiSensitivityPanel';
import BiSettingsQuickLinks from '@/components/bi/BiSettingsQuickLinks';
import BiTenantSecurityForm from '@/components/bi/BiTenantSecurityForm';
import LlmOccupancyPanel from '@/components/LlmOccupancyPanel';
import { PageShell } from '@/components/PageShell';
import { useApiConfig } from '@/context/ApiContext';
import { isRunnerConfigured } from '@/api/client';

/** Branding, security, steward, and ops — analytics canvas lives on /bi. */
export default function BiSettingsPage() {
  const { config } = useApiConfig();
  const runnerOk = isRunnerConfigured(config);

  return (
    <PageShell pageId="biSettings" titleKey="nav.biSettings" subtitleKey="nav.hint.biSettings" maxWidth="max-w-3xl">
      <div className="space-y-6">
        {runnerOk ? <BiOpsHealthPanel /> : null}
        {runnerOk ? <LlmOccupancyPanel config={config} /> : null}
        <BiBrandingSettingsForm />
        {runnerOk ? <BiTenantSecurityForm /> : null}
        {runnerOk ? <BiSensitivityPanel /> : null}
        {runnerOk ? <BiBindingStewardPanel /> : null}
        {runnerOk ? <BiSemanticStewardPanel /> : null}
        <BiSettingsQuickLinks />
      </div>
    </PageShell>
  );
}
