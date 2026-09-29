import { usePermission, useCurrentModal, useRouter, useRouteParameter, useSettingStructure } from '@rocket.chat/ui-contexts';
import type { ReactElement } from 'react';
import { memo, useLayoutEffect } from 'react';

import AdminABACPage from './AdminABACPage';
import type { ABACTab } from './hooks/useABACTabPermissions';
import { ABAC_TAB_ORDER, useABACTabPermissions } from './hooks/useABACTabPermissions';
import PageSkeleton from '../../../components/PageSkeleton';
import { useHasLicenseModule } from '../../../hooks/useHasLicenseModule';
import SettingsProvider from '../../../providers/SettingsProvider';
import NotAuthorizedPage from '../../notAuthorized/NotAuthorizedPage';
import EditableSettingsProvider from '../settings/EditableSettingsProvider';

const AdminABACRoute = (): ReactElement => {
	const canViewABACPage = usePermission('abac-management');
	const { data: hasABAC = false } = useHasLicenseModule('abac');
	const isModalOpen = !!useCurrentModal();
	const tab = useRouteParameter('tab');
	const router = useRouter();
	const tabPermissions = useABACTabPermissions();
	const firstAllowedTab = ABAC_TAB_ORDER.find((t) => tabPermissions[t]);
	const isAllowedTab = (ABAC_TAB_ORDER as readonly string[]).includes(tab ?? '') && tabPermissions[tab as ABACTab];

	const ABACEnabledSetting = useSettingStructure('ABAC_Enabled');

	useLayoutEffect(() => {
		if (firstAllowedTab && !isAllowedTab) {
			router.navigate(
				{
					name: 'admin-ABAC',
					params: { tab: firstAllowedTab },
				},
				{ replace: true },
			);
		}
	}, [router, firstAllowedTab, isAllowedTab]);

	// Zeki: vendor upsell modal removed; unlicensed workspaces fall through to NotAuthorizedPage

	if (isModalOpen) {
		return <PageSkeleton />;
	}

	if (!canViewABACPage || !firstAllowedTab || (ABACEnabledSetting === undefined && !hasABAC)) {
		return <NotAuthorizedPage />;
	}

	return (
		<SettingsProvider>
			<EditableSettingsProvider>
				<AdminABACPage shouldShowWarning={ABACEnabledSetting !== undefined && !hasABAC} />
			</EditableSettingsProvider>
		</SettingsProvider>
	);
};

export default memo(AdminABACRoute);
