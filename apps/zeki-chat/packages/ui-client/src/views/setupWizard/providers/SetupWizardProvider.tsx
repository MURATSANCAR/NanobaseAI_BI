import { useEffectEvent } from '@rocket.chat/fuselage-hooks';
import { validateEmail } from '@rocket.chat/tools';
import {
	useToastMessageDispatch,
	useSessionDispatch,
	useLoginWithPassword,
	useSettingSetValue,
	useSettingsDispatch,
	useMethod,
	useEndpoint,
	useTranslation,
} from '@rocket.chat/ui-contexts';
import type { ReactElement, ContextType } from 'react';
import { useCallback, useMemo, useState } from 'react';

import { clientCallbacks } from '../../../lib';
import { SetupWizardContext } from '../contexts/SetupWizardContext';
import { useParameters } from '../hooks/useParameters';
import { useStepRouting } from '../hooks/useStepRouting';

const initialData: ContextType<typeof SetupWizardContext>['setupWizardData'] = {
	organizationData: {
		organizationName: '',
		organizationIndustry: '',
		organizationSize: '',
		country: '',
	},
};

const SetupWizardProvider = ({ children }: { children: ReactElement }): ReactElement => {
	const t = useTranslation();
	const [setupWizardData, setSetupWizardData] = useState<ContextType<typeof SetupWizardContext>['setupWizardData']>(initialData);
	const [currentStep, setCurrentStep] = useStepRouting();
	const { isSuccess, data } = useParameters();
	const dispatchToastMessage = useToastMessageDispatch();
	const dispatchSettings = useSettingsDispatch();

	const setShowSetupWizard = useSettingSetValue('Show_Setup_Wizard');
	const registerUser = useMethod('registerUser');
	const setBasicInfo = useEndpoint('POST', '/v1/users.updateOwnBasicInfo');
	const loginWithPassword = useLoginWithPassword();
	const setForceLogin = useSessionDispatch('forceLogin');

	const goToPreviousStep = useCallback(() => setCurrentStep((currentStep) => currentStep - 1), [setCurrentStep]);
	const goToNextStep = useCallback(() => setCurrentStep((currentStep) => currentStep + 1), [setCurrentStep]);
	const goToStep = useCallback((step: number) => setCurrentStep(() => step), [setCurrentStep]);

	const _validateEmail = useCallback(
		(email: string): true | string => {
			if (!validateEmail(email)) {
				return t('Invalid_email');
			}

			return true;
		},
		[t],
	);

	const registerAdminUser = useCallback(
		async ({
			fullname,
			username,
			email,
			password,
		}: {
			fullname: string;
			username: string;
			email: string;
			password: string;
		}): Promise<void> => {
			await registerUser({ name: fullname, username, email, pass: password });
			void clientCallbacks.run('userRegistered', {});

			try {
				await loginWithPassword(email, password);
			} catch (error) {
				if ((error as { error?: unknown }).error === 'error-invalid-email') {
					dispatchToastMessage({ type: 'success', message: t('We_have_sent_registration_email') });
					return;
				}
				if (error instanceof Error || typeof error === 'string') {
					dispatchToastMessage({ type: 'error', message: error });
				}
				throw error;
			}

			setForceLogin(false);

			await setBasicInfo({ data: { username } });
			await dispatchSettings([{ _id: 'Organization_Email', value: email }]);
			void clientCallbacks.run('usernameSet', {});
		},
		[registerUser, setForceLogin, setBasicInfo, dispatchSettings, loginWithPassword, dispatchToastMessage, t],
	);

	const saveOrganizationData = useCallback(
		async (organizationData: ContextType<typeof SetupWizardContext>['setupWizardData']['organizationData']): Promise<void> => {
			const { organizationName, organizationIndustry, organizationSize, country } = organizationData;

			await dispatchSettings([
				{
					_id: 'Country',
					value: country,
				},
				{
					_id: 'Industry',
					value: organizationIndustry,
				},
				{
					_id: 'Size',
					value: organizationSize,
				},
				{
					_id: 'Organization_Name',
					value: organizationName,
				},
			]);
		},
		[dispatchSettings],
	);

	const completeSetupWizard = useEffectEvent(async (): Promise<void> => {
		dispatchToastMessage({ type: 'success', message: t('Your_workspace_is_ready') });
		return setShowSetupWizard('completed');
	});

	const value = useMemo(
		() => ({
			setupWizardData,
			setSetupWizardData,
			currentStep,
			loaded: isSuccess,
			settings: data.settings,
			goToPreviousStep,
			goToNextStep,
			goToStep,
			registerAdminUser,
			validateEmail: _validateEmail,
			saveOrganizationData,
			completeSetupWizard,
			maxSteps: 2,
		}),
		[
			setupWizardData,
			currentStep,
			isSuccess,
			data.settings,
			goToPreviousStep,
			goToNextStep,
			goToStep,
			registerAdminUser,
			_validateEmail,
			saveOrganizationData,
			completeSetupWizard,
		],
	);

	return <SetupWizardContext.Provider value={value}>{children}</SetupWizardContext.Provider>;
};

export default SetupWizardProvider;
