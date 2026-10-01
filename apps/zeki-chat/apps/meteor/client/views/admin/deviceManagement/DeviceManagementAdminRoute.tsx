import { usePermission, useCurrentModal } from '@zeki.chat/ui-contexts';
import type { ReactElement } from 'react';

import DeviceManagementAdminPage from './DeviceManagementAdminPage';
import PageSkeleton from '../../../components/PageSkeleton';
import { useHasCapability } from '../../../hooks/useHasCapability';
import NotAuthorizedPage from '../../notAuthorized/NotAuthorizedPage';

const DeviceManagementAdminRoute = (): ReactElement => {
	const isModalOpen = !!useCurrentModal();

	const { data: hasDeviceManagement = false, isPending } = useHasCapability('device-management');
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
