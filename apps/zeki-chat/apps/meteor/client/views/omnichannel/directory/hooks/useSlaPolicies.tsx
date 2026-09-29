import { useEndpoint } from '@zeki.chat/ui-contexts';
import { useQuery } from '@tanstack/react-query';
import { millisecondsToMinutes } from 'date-fns';

import { useHasCapability } from '../../../../hooks/useHasCapability';

export const useSlaPolicies = () => {
	const { data: isEnterprise = false } = useHasCapability('livechat-enterprise');
	const getSlaPolicies = useEndpoint('GET', '/v1/livechat/sla');
	const { data: { sla } = {}, ...props } = useQuery({
		queryKey: ['/v1/livechat/sla'],
		queryFn: () => getSlaPolicies({}),
		staleTime: millisecondsToMinutes(10),
		enabled: isEnterprise,
	});

	return {
		data: sla,
		...props,
	};
};
