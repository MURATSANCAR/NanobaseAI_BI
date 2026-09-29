import { useEndpoint } from '@zeki.chat/ui-contexts';
import { useMutation } from '@tanstack/react-query';

export const useSendTelemetryMutation = () => {
	const sendTelemetry = useEndpoint('POST', '/v1/statistics.telemetry');

	return useMutation({
		mutationFn: sendTelemetry,
		onError: (error) => {
			console.warn(error);
		},
	});
};
