import type { IMessage } from '@zeki.chat/core-typings';
import { useStream } from '@zeki.chat/ui-contexts';
import { useEffect } from 'preact/hooks';

import { onMessage } from '../lib/room';

export const useRoomMessagesSubscription = (rid: string, token: string) => {
	const stream = useStream('room-messages');

	useEffect(() => {
		if (!rid) {
			return;
		}
		return stream(rid, (msg: IMessage) => {
			void onMessage(msg);
		});
	}, [rid, stream, token]);
};
