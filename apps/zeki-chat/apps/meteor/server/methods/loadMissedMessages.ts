import type { IMessage, IRoom } from '@zeki.chat/core-typings';
import type { ServerMethods } from '@zeki.chat/ddp-client';
import { Messages } from '@zeki.chat/models';
import { check } from 'meteor/check';
import { Meteor } from 'meteor/meteor';

import { canAccessRoomIdAsync } from '../../app/authorization/server/functions/canAccessRoom';

declare module '@zeki.chat/ddp-client' {
	// eslint-disable-next-line @typescript-eslint/naming-convention
	interface ServerMethods {
		loadMissedMessages(rid: IRoom['_id'], ts: Date): Promise<false | IMessage[]>;
	}
}

Meteor.methods<ServerMethods>({
	async loadMissedMessages(rid, start) {
		check(rid, String);
		check(start, Date);

		const fromId = Meteor.userId() ?? undefined;

		if (!rid) {
			throw new Meteor.Error('error-invalid-room', 'Invalid room', { method: 'getUsersOfRoom' });
		}

		if (!(await canAccessRoomIdAsync(rid, fromId))) {
			return false;
		}

		return Messages.findVisibleByRoomIdAfterTimestamp(rid, start, true, {
			sort: {
				ts: -1,
			},
		}).toArray();
	},
});
