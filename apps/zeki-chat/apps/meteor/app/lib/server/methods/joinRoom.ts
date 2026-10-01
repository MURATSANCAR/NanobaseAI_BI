import { Room } from '@zeki.chat/core-services';
import type { IRoom } from '@zeki.chat/core-typings';
import type { ServerMethods } from '@zeki.chat/ddp-client';
import { Rooms } from '@zeki.chat/models';
import { check } from 'meteor/check';
import { Meteor } from 'meteor/meteor';

declare module '@zeki.chat/ddp-client' {
	// eslint-disable-next-line @typescript-eslint/naming-convention
	interface ServerMethods {
		joinRoom(rid: IRoom['_id'], code?: string): boolean | undefined;
	}
}

Meteor.methods<ServerMethods>({
	async joinRoom(rid, code) {
		check(rid, String);

		const user = await Meteor.userAsync();
		if (!user) {
			throw new Meteor.Error('error-invalid-user', 'Invalid user', { method: 'joinRoom' });
		}

		const room = await Rooms.findOneById(rid);
		if (!room) {
			throw new Meteor.Error('error-invalid-room', 'Invalid room', { method: 'joinRoom' });
		}

		return Room.join({ room, user, ...(code ? { joinCode: code } : {}) });
	},
});
