import type { ServerMethods } from '@zeki.chat/ddp-client';
import { Subscriptions } from '@zeki.chat/models';
import { check } from 'meteor/check';
import { Meteor } from 'meteor/meteor';

import { notifyOnSubscriptionChangedByRoomIdAndUserIds } from '../lib/notifyListener';

declare module '@zeki.chat/ddp-client' {
	// eslint-disable-next-line @typescript-eslint/naming-convention
	interface ServerMethods {
		unblockUser({ rid, blocked }: { rid: string; blocked: string }): boolean;
	}
}

Meteor.methods<ServerMethods>({
	async unblockUser({ rid, blocked }) {
		check(rid, String);
		check(blocked, String);
		const userId = Meteor.userId();

		if (!userId) {
			throw new Meteor.Error('error-invalid-user', 'Invalid user', { method: 'blockUser' });
		}

		const [blockedUser, blockerUser] = await Promise.all([
			Subscriptions.findOneByRoomIdAndUserId(rid, blocked, { projection: { _id: 1 } }),
			Subscriptions.findOneByRoomIdAndUserId(rid, userId, { projection: { _id: 1 } }),
		]);

		if (!blockedUser || !blockerUser) {
			throw new Meteor.Error('error-invalid-room', 'Invalid room', { method: 'blockUser' });
		}

		const [blockedResponse, blockerResponse] = await Subscriptions.unsetBlockedByRoomId(rid, blocked, userId);

		const listenerUsers = [...(blockedResponse?.modifiedCount ? [blocked] : []), ...(blockerResponse?.modifiedCount ? [userId] : [])];

		if (listenerUsers.length) {
			void notifyOnSubscriptionChangedByRoomIdAndUserIds(rid, listenerUsers);
		}

		return true;
	},
});
