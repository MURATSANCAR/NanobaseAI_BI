import type { IUser } from '@zeki.chat/core-typings';
import type { ServerMethods } from '@zeki.chat/ddp-client';
import { Match, check } from 'meteor/check';
import { Meteor } from 'meteor/meteor';

import { addUserToDefaultChannels } from '../functions/addUserToDefaultChannels';

declare module '@zeki.chat/ddp-client' {
	// eslint-disable-next-line @typescript-eslint/naming-convention
	interface ServerMethods {
		joinDefaultChannels(silenced?: boolean): void;
	}
}

Meteor.methods<ServerMethods>({
	async joinDefaultChannels(silenced) {
		check(silenced, Match.Optional(Boolean));
		const user = await Meteor.userAsync();

		if (!user) {
			throw new Meteor.Error('error-invalid-user', 'Invalid user', {
				method: 'joinDefaultChannels',
			});
		}
		return addUserToDefaultChannels(user as IUser, Boolean(silenced));
	},
});
