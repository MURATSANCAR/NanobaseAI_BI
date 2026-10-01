import { useUserId } from '@zeki.chat/ui-contexts';
import { useEffect } from 'react';

import { fireGlobalEvent } from '../../../lib/utils/fireGlobalEvent';

export const useCustomScript = (): void => {
	const uid = useUserId();
	useEffect(() => {
		if (uid) {
			fireGlobalEvent('Custom_Script_Logged_In');
			return;
		}

		fireGlobalEvent('Custom_Script_Logged_Out');
	}, [uid]);
};
