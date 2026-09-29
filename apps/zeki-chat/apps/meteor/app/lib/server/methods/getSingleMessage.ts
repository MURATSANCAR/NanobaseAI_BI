import type { IMessage } from '@zeki.chat/core-typings';
import type { ServerMethods } from '@zeki.chat/ddp-client';
import { Messages } from '@zeki.chat/models';
import { check } from 'meteor/check';
import { Meteor } from 'meteor/meteor';

import { canAccessRoomIdAsync } from '../../../authorization/server/functions/canAccessRoom';

declare module '@zeki.chat/ddp-client' {
	// eslint-disable-next-line @typescript-eslint/naming-convention
	interface ServerMethods {
		getSingleMessage(mid: IMessage['_id']): Promise<IMessage | null>;
	}
}

export const getSingleMessage = async (userId: string, mid: IMessage['_id']): Promise<IMessage | null> => {
	const msg = await Messages.findOneById(mid);

	if (!msg?.rid) {
		return null;
	}

	if (!(await canAccessRoomIdAsync(msg.rid, userId))) {
		throw new Meteor.Error('error-not-allowed', 'Not allowed', { method: 'getSingleMessage' });
	}

	return msg;
};

Meteor.methods<ServerMethods>({
	async getSingleMessage(mid) {
		check(mid, String);

		const uid = Meteor.userId();

		if (!uid) {
			throw new Meteor.Error('error-invalid-user', 'Invalid user', { method: 'getSingleMessage' });
		}

		return getSingleMessage(uid, mid);
	},
});
