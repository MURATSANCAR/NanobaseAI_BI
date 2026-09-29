import { usePermission } from '@zeki.chat/ui-contexts';

import UnitsPage from './UnitsPage';
import { useHasCapability } from '../../../hooks/useHasCapability';
import NotAuthorizedPage from '../../notAuthorized/NotAuthorizedPage';

const UnitsRoute = () => {
	const canViewUnits = usePermission('manage-livechat-units');
	const { data: isEnterprise = false } = useHasCapability('livechat-enterprise');

	if (!(isEnterprise && canViewUnits)) {
		return <NotAuthorizedPage />;
	}

	return <UnitsPage />;
};

export default UnitsRoute;
