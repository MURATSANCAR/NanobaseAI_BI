import type { ServerMethods } from '@zeki.chat/ddp-client';
import { Subscriptions } from '@zeki.chat/models';
import { check } from 'meteor/check';
import { Meteor } from 'meteor/meteor';

import { notifyOnSubscriptionChangedByRoomIdAndUserId } from '../../app/lib/server/lib/notifyListener';

declare module '@zeki.chat/ddp-client' {
	// eslint-disable-next-line @typescript-eslint/naming-convention
	interface ServerMethods {
		hideRoom(rid: string): Promise<number>;
	}
}

export const hideRoomMethod = async (userId: string, rid: string): Promise<number> => {
	check(rid, String);

	if (!userId) {
		throw new Meteor.Error('error-invalid-user', 'Invalid user', {
			method: 'hideRoom',
		});
	}

	const { modifiedCount } = await Subscriptions.hideByRoomIdAndUserId(rid, userId);

	if (modifiedCount) {
		void notifyOnSubscriptionChangedByRoomIdAndUserId(rid, userId);
	}

	return modifiedCount;
};

Meteor.methods<ServerMethods>({
	async hideRoom(rid) {
		const uid = Meteor.userId();

		if (!uid) {
			throw new Meteor.Error('error-invalid-user', 'Invalid user', {
				method: 'hideRoom',
			});
		}

		return hideRoomMethod(uid, rid);
	},
});
