import { isMessageFromVisitor } from '@zeki.chat/core-typings';
import { LivechatRooms } from '@zeki.chat/models';

import { callbacks } from '../../../../server/lib/callbacks';

callbacks.add(
	'afterOmnichannelSaveMessage',
	async (message, { roomUpdater }) => {
		if (message.t || !isMessageFromVisitor(message)) {
			return message;
		}

		await LivechatRooms.getVisitorLastMessageTsUpdateQueryByRoomId(message.ts, roomUpdater);

		return message;
	},
	callbacks.priority.HIGH,
	'save-last-visitor-message-timestamp',
);
