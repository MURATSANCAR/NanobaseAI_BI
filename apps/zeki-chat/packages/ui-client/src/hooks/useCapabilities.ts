import type { Serialized } from '@rocket.chat/core-typings';
import type { OperationResult } from '@rocket.chat/rest-typings';
import { useEndpoint, useStream, useUserId } from '@rocket.chat/ui-contexts';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useCallback, useEffect } from 'react';

type CapabilitiesData = Serialized<Awaited<OperationResult<'GET', '/v1/capabilities.info'>>>;

export const useInvalidateCapabilities = () => {
	const queryClient = useQueryClient();
	return useCallback(() => queryClient.invalidateQueries({ queryKey: ['capabilities'] }), [queryClient]);
};

export const useCapabilitiesBase = <TData = CapabilitiesData>({ select, enabled = true }: {
	select: (data: CapabilitiesData) => TData;
	enabled?: boolean;
}) => {
	const uid = useUserId();
	const getCapabilities = useEndpoint('GET', '/v1/capabilities.info');
	const invalidate = useInvalidateCapabilities();
	const notify = useStream('notify-all');
	useEffect(() => notify('capabilities', () => { void invalidate(); }), [notify, invalidate]);
	return useQuery({
		queryKey: ['capabilities', 'info'],
		queryFn: () => getCapabilities(),
		staleTime: Infinity,
		select,
		enabled: enabled && !!uid,
	});
};

export const useCapabilities = () => useCapabilitiesBase({ select: (data) => data.capabilities });
