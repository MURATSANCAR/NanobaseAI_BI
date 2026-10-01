import type { ServerMethods } from '@zeki.chat/ddp-client';
import { Rooms } from '@zeki.chat/models';
import { Meteor } from 'meteor/meteor';

declare module '@zeki.chat/ddp-client' {
	// eslint-disable-next-line @typescript-eslint/naming-convention
	interface ServerMethods {
		getTotalChannels(): number;
	}
}

Meteor.methods<ServerMethods>({
	getTotalChannels() {
		if (!Meteor.userId()) {
			throw new Meteor.Error('error-invalid-user', 'Invalid user', {
				method: 'getTotalChannels',
			});
		}

		return Rooms.countDocuments({ t: 'c' });
	},
});
