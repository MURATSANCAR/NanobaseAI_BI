import { useSetModal } from '@zeki.chat/ui-contexts';
import { useCallback } from 'react';

import VideoConfBlockModal from '../VideoConfBlockModal';

export const useVideoConfOpenCall = () => {
	const setModal = useSetModal();

	const handleOpenCall = useCallback(
		(callUrl: string, providerName?: string | undefined) => {
			const desktopApp = window.ZekiChatDesktop;

			if (!desktopApp?.openInternalVideoChatWindow) {
				const open = () => window.open(callUrl);
				const popup = open();

				if (popup !== null) {
					return;
				}

				setModal(<VideoConfBlockModal onClose={(): void => setModal(null)} onConfirm={open} />);
				return;
			}
			desktopApp.openInternalVideoChatWindow(callUrl, { providerName });
		},
		[setModal],
	);

	return handleOpenCall;
};
