import type { ReactElement } from 'react';

import { useSetupWizardContext } from './contexts/SetupWizardContext';
import AdminInfoStep from './steps/AdminInfoStep';
import OrganizationInfoStep from './steps/OrganizationInfoStep';

// Zeki: the Rocket.Chat Cloud register/confirmation steps were removed; the wizard has two local steps only.
const SetupWizardPage = (): ReactElement => {
	const { currentStep } = useSetupWizardContext();

	switch (currentStep) {
		case 1:
			return <AdminInfoStep />;
		case 2:
			return <OrganizationInfoStep />;

		default:
			throw new Error('Wrong wizard step');
	}
};

export default SetupWizardPage;
