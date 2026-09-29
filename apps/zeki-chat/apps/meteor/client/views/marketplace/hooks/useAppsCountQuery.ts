import { useEndpoint } from '@zeki.chat/ui-contexts';
import { useQueryClient, useQuery } from '@tanstack/react-query';
import { useCallback } from 'react';

export type MarketplaceRouteContext = 'private' | 'explore' | 'installed' | 'premium' | 'requested' | 'details';

export function isMarketplaceRouteContext(context: string): context is MarketplaceRouteContext {
	return ['private', 'explore', 'installed', 'premium', 'requested'].includes(context);
}

export const useAppsCountQuery = (context: MarketplaceRouteContext) => {
	const getAppsCount = useEndpoint('GET', '/apps/count');

	return useQuery({
		queryKey: ['apps/count', context],

		queryFn: async () => {
			const data = await getAppsCount();

			const numberOfEnabledApps = context === 'private' ? data.totalPrivateEnabled : data.totalMarketplaceEnabled;
			return { enabled: numberOfEnabledApps };
		},

		staleTime: 10_000,
	});
};

export const useInvalidateAppsCountQueryCallback = () => {
	const queryClient = useQueryClient();
	return useCallback(() => {
		queryClient.invalidateQueries({
			queryKey: ['apps/count'],
		});
	}, [queryClient]);
};
