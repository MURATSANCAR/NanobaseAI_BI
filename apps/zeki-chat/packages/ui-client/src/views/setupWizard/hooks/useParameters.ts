import type { ISetting } from '@zeki.chat/core-typings';
import { useMethod } from '@zeki.chat/ui-contexts';
import type { UseQueryResult } from '@tanstack/react-query';
import { useQuery } from '@tanstack/react-query';

type SetupWizardParameters = {
	settings: ISetting[];
	serverAlreadyRegistered: boolean;
};

export const useParameters = (): Exclude<UseQueryResult<SetupWizardParameters, Error>, { data: undefined }> => {
	const getSetupWizardParameters = useMethod('getSetupWizardParameters');

	return useQuery({
		queryKey: ['setupWizard/parameters'],
		queryFn: getSetupWizardParameters,
		initialData: {
			settings: [],
			serverAlreadyRegistered: false,
		},
	}) as Exclude<UseQueryResult<SetupWizardParameters, Error>, { data: undefined }>;
};
