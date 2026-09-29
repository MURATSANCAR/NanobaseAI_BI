import { useEffectEvent } from '@rocket.chat/fuselage-hooks';
import { ContextualbarHeader, ContextualbarTitle, ContextualbarClose, ContextualbarDialog } from '@rocket.chat/ui-client';
import { useRouteParameter, useRoute, useTranslation } from '@rocket.chat/ui-contexts';
import type { ReactElement } from 'react';
import { useEffect } from 'react';

import EditRolePageWithData from './EditRolePageWithData';
import { useHasLicenseModule } from '../../../hooks/useHasLicenseModule';

const PermissionsContextBar = (): ReactElement | null => {
	const t = useTranslation();
	const _id = useRouteParameter('_id');
	const context = useRouteParameter('context');
	const router = useRoute('admin-permissions');
	const { isPending, data: hasCustomRolesModule = false } = useHasLicenseModule('custom-roles');

	const handleCloseContextualbar = useEffectEvent(() => {
		router.push({});
	});

	useEffect(() => {
		if (isPending) {
			return;
		}

		if (context !== 'new' || hasCustomRolesModule) {
			return;
		}

		// Zeki: vendor upsell modal removed
		handleCloseContextualbar();
	}, [isPending, context, hasCustomRolesModule, handleCloseContextualbar]);

	return (
		(context && (
			<ContextualbarDialog onClose={handleCloseContextualbar}>
				<ContextualbarHeader>
					<ContextualbarTitle>{context === 'edit' ? t('Role_Editing') : t('New_role')}</ContextualbarTitle>
					<ContextualbarClose onClick={handleCloseContextualbar} />
				</ContextualbarHeader>
				<EditRolePageWithData roleId={_id} />
			</ContextualbarDialog>
		)) ||
		null
	);
};

export default PermissionsContextBar;
