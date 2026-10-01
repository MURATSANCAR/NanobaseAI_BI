import type { IRoom } from '@zeki.chat/core-typings';
import type { ServerMethods } from '@zeki.chat/ddp-client';
import { check } from 'meteor/check';
import { Meteor } from 'meteor/meteor';

import { openRoom } from '../lib/openRoom';

declare module '@zeki.chat/ddp-client' {
	// eslint-disable-next-line @typescript-eslint/naming-convention
	interface ServerMethods {
		openRoom(rid: IRoom['_id']): Promise<number>;
	}
}

Meteor.methods<ServerMethods>({
	async openRoom(rid) {
		check(rid, String);

		const uid = Meteor.userId();

		if (!uid) {
			throw new Meteor.Error('error-invalid-user', 'Invalid user', {
				method: 'openRoom',
			});
		}

		return openRoom(uid, rid);
	},
});
