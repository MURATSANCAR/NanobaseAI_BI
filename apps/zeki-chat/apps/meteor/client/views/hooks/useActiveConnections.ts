import { useEndpoint } from '@zeki.chat/ui-contexts';
import type { UseQueryResult } from '@tanstack/react-query';
import { useQuery } from '@tanstack/react-query';

export const useActiveConnections = (): UseQueryResult<{ current: number }> => {
	const getConnections = useEndpoint('GET', '/v1/presence.getConnections');
	return useQuery({
		queryKey: ['userConnections'],

		queryFn: async () => {
			const { current } = await getConnections();
			return { current };
		},

		staleTime: 1000 * 60,
	});
};
