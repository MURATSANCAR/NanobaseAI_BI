import { isRoomWithJoinCode } from '@zeki.chat/core-typings';
import type { ServerMethods } from '@zeki.chat/ddp-client';
import { Rooms } from '@zeki.chat/models';
import { check } from 'meteor/check';
import { Meteor } from 'meteor/meteor';

import { hasPermissionAsync } from '../../../authorization/server/functions/hasPermission';

declare module '@zeki.chat/ddp-client' {
	// eslint-disable-next-line @typescript-eslint/naming-convention
	interface ServerMethods {
		getRoomJoinCode(rid: string): string | false;
	}
}
/* @deprecated */
Meteor.methods<ServerMethods>({
	async getRoomJoinCode(rid) {
		check(rid, String);

		const userId = Meteor.userId();

		if (!userId) {
			throw new Meteor.Error('error-invalid-user', 'Invalid user', { method: 'getJoinCode' });
		}

		if (!(await hasPermissionAsync(userId, 'view-join-code'))) {
			throw new Meteor.Error('error-not-authorized', 'Not authorized', { method: 'getJoinCode' });
		}

		const room = await Rooms.findById(rid);

		// eslint-disable-next-line @typescript-eslint/no-non-null-assertion
		return Boolean(room) && (isRoomWithJoinCode(room!) ? room.joinCode : false);
	},
});
