import { useEndpoint } from '@zeki.chat/ui-contexts';
import { useMutation } from '@tanstack/react-query';

export const useSendForgotPassword = () => {
	const sendForgotPassword = useEndpoint('POST', '/v1/users.forgotPassword');

	return useMutation({
		mutationFn: sendForgotPassword,
	});
};
