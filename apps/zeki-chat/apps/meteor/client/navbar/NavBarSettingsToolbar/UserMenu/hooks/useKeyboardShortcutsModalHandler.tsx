import { useSetModal } from '@zeki.chat/ui-contexts';

import KeyboardShortcutsModal from '../KeyboardShortcutsModal';

export const useKeyboardShortcutsModalHandler = () => {
	const setModal = useSetModal();

	return () => {
		const handleModalClose = () => setModal(null);
		setModal(<KeyboardShortcutsModal onClose={handleModalClose} />);
	};
};
