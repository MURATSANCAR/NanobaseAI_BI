import { useRouteParameter, useRouter, useRole, useSetting } from '@rocket.chat/ui-contexts';
import type { Dispatch, SetStateAction } from 'react';
import { useState, useEffect } from 'react';

// Zeki: the wizard only has two local steps (admin info, organization info); cloud registration steps were removed.
const LAST_STEP = 2;

export const useStepRouting = (): [number, Dispatch<SetStateAction<number>>] => {
	const param = useRouteParameter('step');
	const router = useRouter();
	const hasAdminRole = useRole('admin');
	const hasOrganizationData = !!useSetting('Organization_Name');

	const [currentStep, setCurrentStep] = useState<number>(() => {
		const initialStep = hasOrganizationData || hasAdminRole ? LAST_STEP : 1;

		if (!param) {
			return initialStep;
		}

		const step = parseInt(param, 10);
		if (step && Number.isFinite(step) && step >= 1) {
			return Math.min(step, LAST_STEP);
		}

		return initialStep;
	});

	useEffect(() => {
		switch (true) {
			case currentStep > LAST_STEP: {
				setCurrentStep(LAST_STEP);
				router.navigate(`/setup-wizard/${LAST_STEP}`);
				break;
			}

			case currentStep === 1 && (hasAdminRole || hasOrganizationData): {
				setCurrentStep(LAST_STEP);
				router.navigate(`/setup-wizard/${LAST_STEP}`);
				break;
			}

			default: {
				router.navigate(`/setup-wizard/${currentStep}`);
			}
		}
	}, [router, currentStep, hasAdminRole, hasOrganizationData]);

	return [currentStep, setCurrentStep];
};
