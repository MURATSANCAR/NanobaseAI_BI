import type { OperationResult } from '@zeki.chat/rest-typings';
import { useEndpoint } from '@zeki.chat/ui-contexts';
import type { UseQueryResult } from '@tanstack/react-query';
import { useQuery } from '@tanstack/react-query';

export const useFeaturedApps = (): UseQueryResult<OperationResult<'GET', '/apps/featured-apps'>> => {
	const featuredApps = useEndpoint('GET', '/apps/featured-apps');

	return useQuery({
		queryKey: ['featured-apps'],
		queryFn: () => featuredApps(),
	});
};
