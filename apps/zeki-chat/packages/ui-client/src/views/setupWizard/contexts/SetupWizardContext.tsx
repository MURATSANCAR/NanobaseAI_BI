import type { ISetting } from '@zeki.chat/core-typings';
import type AdminInfoPage from '../components/AdminInfoPage';
import type OrganizationInfoPage from '../components/OrganizationInfoPage';
import type { ComponentProps, Dispatch, SetStateAction } from 'react';
import { createContext, useContext } from 'react';

type SetupWizardData = {
	organizationData: Parameters<ComponentProps<typeof OrganizationInfoPage>['onSubmit']>[0];
};

type SetupWizarContextValue = {
	setupWizardData: SetupWizardData;
	setSetupWizardData: Dispatch<SetStateAction<SetupWizardData>>;
	loaded: boolean;
	settings: Array<ISetting>;
	currentStep: number;
	validateEmail: (email: string) => string | true;
	goToPreviousStep: () => void;
	goToNextStep: () => void;
	goToStep: (step: number) => void;
	registerAdminUser: (user: Omit<Parameters<ComponentProps<typeof AdminInfoPage>['onSubmit']>[0], 'keepPosted'>) => Promise<void>;
	saveOrganizationData: (data: SetupWizardData['organizationData']) => Promise<void>;
	completeSetupWizard: () => Promise<void>;
	maxSteps: number;
};

export const SetupWizardContext = createContext<SetupWizarContextValue>({
	setupWizardData: {
		organizationData: {
			organizationName: '',
			organizationIndustry: '',
			organizationSize: '',
			country: '',
		},
	},
	setSetupWizardData: (data) => data,
	loaded: false,
	settings: [],
	goToPreviousStep: () => undefined,
	goToNextStep: () => undefined,
	goToStep: () => undefined,
	registerAdminUser: async () => undefined,
	saveOrganizationData: async () => undefined,
	validateEmail: () => true,
	currentStep: 1,
	completeSetupWizard: async () => undefined,
	maxSteps: 2,
});

export const useSetupWizardContext = (): SetupWizarContextValue => useContext(SetupWizardContext);
