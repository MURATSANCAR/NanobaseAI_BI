import { Message } from '@zeki.chat/core-services';
import type { IMessage } from '@zeki.chat/core-typings';
import { Rooms, Subscriptions } from '@zeki.chat/models';

import { callbacks } from '../../../../server/lib/callbacks';
import { notifyOnRoomChanged, notifyOnSubscriptionChangedByRoomId } from '../lib/notifyListener';

export const archiveRoom = async function (rid: string, user: IMessage['u']): Promise<void> {
	await Rooms.archiveById(rid);

	const archiveResponse = await Subscriptions.archiveByRoomId(rid);
	if (archiveResponse.modifiedCount) {
		void notifyOnSubscriptionChangedByRoomId(rid);
	}

	await Message.saveSystemMessage('room-archived', rid, '', user);

	const room = await Rooms.findOneById(rid);

	await callbacks.run('afterRoomArchived', room, user);

	if (room) {
		void notifyOnRoomChanged(room);
	}
};
