import { Presence } from '@zeki.chat/core-services';
import { UserStatus } from '@zeki.chat/core-typings';
import type { ServerMethods } from '@zeki.chat/ddp-client';
import { Meteor } from 'meteor/meteor';

declare module '@zeki.chat/ddp-client' {
	// eslint-disable-next-line @typescript-eslint/naming-convention
	interface ServerMethods {
		'UserPresence:setDefaultStatus'(status: UserStatus): boolean | undefined;
		'UserPresence:online'(): boolean | undefined;
		'UserPresence:away'(): boolean | undefined;
	}
}

Meteor.methods<ServerMethods>({
	'UserPresence:setDefaultStatus'(status) {
		const { userId } = this;
		if (!userId) {
			return;
		}
		return Presence.setStatus(userId, status);
	},
	'UserPresence:online'() {
		const { userId, connection } = this;
		if (!userId || !connection) {
			return;
		}
		return Presence.setConnectionStatus(userId, UserStatus.ONLINE, connection.id);
	},
	'UserPresence:away'() {
		const { userId, connection } = this;
		if (!userId || !connection) {
			return;
		}
		return Presence.setConnectionStatus(userId, UserStatus.AWAY, connection.id);
	},
});
