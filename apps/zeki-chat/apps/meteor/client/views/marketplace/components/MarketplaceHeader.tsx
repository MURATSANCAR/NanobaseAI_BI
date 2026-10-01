import { Button, ButtonGroup } from '@rocket.chat/fuselage';
import { PageHeader } from '@zeki.chat/ui-client';
import { usePermission, useRoute, useRouteParameter } from '@zeki.chat/ui-contexts';
import type { ReactElement } from 'react';
import { useTranslation } from 'react-i18next';

const MarketplaceHeader = ({ title }: { title: string; unsupportedVersion: boolean }): ReactElement | null => {
	const { t } = useTranslation();
	const isAdmin = usePermission('manage-apps');
	const context = (useRouteParameter('context') || 'explore') as 'private' | 'explore' | 'installed' | 'premium' | 'requested';
	const route = useRoute('marketplace');

	// Zeki: vendor upgrade prompt removed; private app upload proceeds directly
	const handleClickPrivate = () => {
		route.push({ context, page: 'install' });
	};

	return (
		<PageHeader title={title}>

			<ButtonGroup wrap align='end'>
				{isAdmin && context === 'private' && <Button onClick={handleClickPrivate}>{t('Upload_private_app')}</Button>}

			</ButtonGroup>
		</PageHeader>
	);
};

export default MarketplaceHeader;
