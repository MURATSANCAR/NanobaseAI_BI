import { useRouteParameter, useRoute, usePermission, useSetting } from '@rocket.chat/ui-contexts';
import type { ReactElement } from 'react';
import { useState, useEffect } from 'react';

import AppDetailsPage from './AppDetailsPage';
import AppInstallPage from './AppInstallPage';
import AppsPage from './AppsPage';
import PageSkeleton from '../../components/PageSkeleton';
import AppsProvider from '../../providers/AppsProvider';
import NotAuthorizedPage from '../notAuthorized/NotAuthorizedPage';

const AppsRoute = (): ReactElement => {
	const localOnly = useSetting('Zeki_Local_Only', true);
	const [isLoading, setLoading] = useState(true);
	const marketplaceRoute = useRoute('marketplace');

	const context = useRouteParameter('context') || 'explore';
	const id = useRouteParameter('id');
	const page = useRouteParameter('page');

	const isAdminUser = usePermission('manage-apps');
	const canAccessMarketplace = usePermission('access-marketplace');

	if (!localOnly && !page) marketplaceRoute.push({ context, page: 'list' });

	useEffect(() => {
		let mounted = true;

		const initialize = async (): Promise<void> => {
			if (!mounted) {
				return;
			}

			setLoading(false);
		};

		initialize();

		return (): void => {
			mounted = false;
		};
	}, [marketplaceRoute, context]);

	if (localOnly) return <NotAuthorizedPage />;

	if (
		(context === 'explore' || context === 'installed' || context === 'private' || context === 'premium') &&
		!canAccessMarketplace &&
		!isAdminUser
	) {
		return <NotAuthorizedPage />;
	}

	if ((context === 'requested' || page === 'install') && !isAdminUser) return <NotAuthorizedPage />;

	if (isLoading) {
		return <PageSkeleton />;
	}

	return (
		<AppsProvider>
			{(page === 'list' && <AppsPage />) ||
				(id && page === 'info' && <AppDetailsPage id={id} />) ||
				(page === 'install' && <AppInstallPage />)}
		</AppsProvider>
	);
};

export default AppsRoute;
