import { Message } from '@zeki.chat/core-services';
import type { IUser } from '@zeki.chat/core-typings';
import { isRegisterUser } from '@zeki.chat/core-typings';
import { Rooms, Subscriptions } from '@zeki.chat/models';
import { Match } from 'meteor/check';
import { Meteor } from 'meteor/meteor';
import type { UpdateResult } from 'mongodb';

import { notifyOnSubscriptionChangedByRoomId } from '../../../lib/server/lib/notifyListener';

export const saveRoomEncrypted = async function (rid: string, encrypted: boolean, user: IUser, sendMessage = true): Promise<UpdateResult> {
	if (!Match.test(rid, String)) {
		throw new Meteor.Error('invalid-room', 'Invalid room', {
			function: 'ZekiChat.saveRoomEncrypted',
		});
	}

	if (!isRegisterUser(user)) {
		throw new Meteor.Error('invalid-user', 'Invalid user', {
			function: 'ZekiChat.saveRoomEncrypted',
		});
	}

	const update = await Rooms.saveEncryptedById(rid, encrypted);
	if (update && sendMessage) {
		const type = encrypted ? 'room_e2e_enabled' : 'room_e2e_disabled';

		await Message.saveSystemMessage(type, rid, user.username, user);
	}

	if (encrypted) {
		const { modifiedCount } = await Subscriptions.disableAutoTranslateByRoomId(rid);
		if (modifiedCount) {
			void notifyOnSubscriptionChangedByRoomId(rid);
		}
	}
	return update;
};
