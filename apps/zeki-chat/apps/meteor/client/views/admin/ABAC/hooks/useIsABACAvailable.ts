import { useSetting } from '@rocket.chat/ui-contexts';

import { useHasCapability } from '../../../../hooks/useHasCapability';

export const useIsABACAvailable = () => {
	const { data: hasABAC = false } = useHasCapability('abac');
	const isABACSettingEnabled = useSetting('ABAC_Enabled', false);

	return hasABAC && isABACSettingEnabled;
};
