import { useMethod, useToastMessageDispatch } from '@zeki.chat/ui-contexts';
import { useMutation } from '@tanstack/react-query';

export const useDismissUserBannerMutation = () => {
	const dismissBanner = useMethod('banner/dismiss');

	const dispatchToastMessage = useToastMessageDispatch();

	return useMutation({
		mutationFn: dismissBanner,
		onError: (error) => {
			dispatchToastMessage({ type: 'error', message: error });
		},
	});
};
