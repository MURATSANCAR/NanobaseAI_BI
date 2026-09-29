import { Button, ButtonGroup, Margins } from '@rocket.chat/fuselage';
import { PageHeader } from '@rocket.chat/ui-client';
import { usePermission, useRoute, useRouteParameter } from '@rocket.chat/ui-contexts';
import type { ReactElement } from 'react';
import { useTranslation } from 'react-i18next';

import { GenericResourceUsageSkeleton } from '../../../components/GenericResourceUsage';
import EnabledAppsCount from './EnabledAppsCount';
import { useAppsCountQuery } from '../hooks/useAppsCountQuery';
import { usePrivateAppsEnabled } from '../hooks/usePrivateAppsEnabled';

const MarketplaceHeader = ({ title, unsupportedVersion }: { title: string; unsupportedVersion: boolean }): ReactElement | null => {
	const { t } = useTranslation();
	const isAdmin = usePermission('manage-apps');
	const context = (useRouteParameter('context') || 'explore') as 'private' | 'explore' | 'installed' | 'premium' | 'requested';
	const route = useRoute('marketplace');
	const result = useAppsCountQuery(context);

	const privateAppsEnabled = usePrivateAppsEnabled();

	// Zeki: vendor upgrade prompt removed; private app upload proceeds directly
	const handleClickPrivate = () => {
		route.push({ context, page: 'install' });
	};

	if (result.isError) {
		return null;
	}

	return (
		<PageHeader title={title}>
			{result.isLoading && <GenericResourceUsageSkeleton mi={16} />}

			{!unsupportedVersion && result.isSuccess && !result.data.hasUnlimitedApps && (
				<Margins inline={16}>
					<EnabledAppsCount
						{...result.data}
						tooltip={context === 'private' && !privateAppsEnabled ? t('Private_apps_premium_message') : undefined}
						context={context}
					/>
				</Margins>
			)}

			<ButtonGroup wrap align='end'>
				{isAdmin && context === 'private' && <Button onClick={handleClickPrivate}>{t('Upload_private_app')}</Button>}

			</ButtonGroup>
		</PageHeader>
	);
};

export default MarketplaceHeader;
