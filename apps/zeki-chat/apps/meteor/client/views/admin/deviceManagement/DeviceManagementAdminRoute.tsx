import { usePermission, useCurrentModal } from '@rocket.chat/ui-contexts';
import type { ReactElement } from 'react';

import DeviceManagementAdminPage from './DeviceManagementAdminPage';
import PageSkeleton from '../../../components/PageSkeleton';
import { useHasLicenseModule } from '../../../hooks/useHasLicenseModule';
import NotAuthorizedPage from '../../notAuthorized/NotAuthorizedPage';

const DeviceManagementAdminRoute = (): ReactElement => {
	const isModalOpen = !!useCurrentModal();

	const { data: hasDeviceManagement = false, isPending } = useHasLicenseModule('device-management');
	const canViewDeviceManagement = usePermission('view-device-management');

	// Zeki: vendor upsell modal removed

	if (isModalOpen || isPending) {
		return <PageSkeleton />;
	}

	if (!canViewDeviceManagement || !hasDeviceManagement) {
		return <NotAuthorizedPage />;
	}

	return <DeviceManagementAdminPage />;
};

export default DeviceManagementAdminRoute;
