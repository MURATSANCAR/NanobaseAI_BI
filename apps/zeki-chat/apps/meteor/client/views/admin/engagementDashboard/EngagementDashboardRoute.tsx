import { usePermission, useRouter, useCurrentModal, useRouteParameter, useEndpoint } from '@zeki.chat/ui-contexts';
import type { ReactElement } from 'react';
import { useEffect } from 'react';

import EngagementDashboardPage from './EngagementDashboardPage';
import PageSkeleton from '../../../components/PageSkeleton';
import { useHasCapability } from '../../../hooks/useHasCapability';
import NotAuthorizedPage from '../../notAuthorized/NotAuthorizedPage';

const isValidTab = (tab: string | undefined): tab is 'users' | 'messages' | 'channels' =>
	typeof tab === 'string' && ['users', 'messages', 'channels'].includes(tab);

const EngagementDashboardRoute = (): ReactElement | null => {
	const canViewEngagementDashboard = usePermission('view-engagement-dashboard');
	const isModalOpen = !!useCurrentModal();

	const router = useRouter();
	const tab = useRouteParameter('tab');
	const eventStats = useEndpoint('POST', '/v1/statistics.telemetry');

	const { isPending, data: hasEngagementDashboard = false } = useHasCapability('engagement-dashboard');

	// Zeki: vendor upsell modal removed

	useEffect(() => {
		return router.subscribeToRouteChange(() => {
			if (!isValidTab(tab)) {
				router.navigate(
					{
						pattern: '/admin/engagement/:tab?',
						params: { tab: 'users' },
					},
					{ replace: true },
				);
			}
		});
	}, [router, tab]);

	if (isModalOpen || isPending) {
		return <PageSkeleton />;
	}

	if (!canViewEngagementDashboard || !hasEngagementDashboard) {
		return <NotAuthorizedPage />;
	}

	eventStats({
		params: [{ eventName: 'updateCounter', settingsId: 'Engagement_Dashboard_Load_Count' }],
	});

	return (
		<EngagementDashboardPage
			tab={tab as 'users' | 'messages' | 'channels'}
			onSelectTab={(tab) =>
				router.navigate({
					pattern: '/admin/engagement/:tab?',
					params: { tab },
				})
			}
		/>
	);
};

export default EngagementDashboardRoute;
