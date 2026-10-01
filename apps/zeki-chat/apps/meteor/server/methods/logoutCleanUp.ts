import { AppEvents, Apps } from '@zeki.chat/apps';
import type { IUser } from '@zeki.chat/core-typings';
import type { ServerMethods } from '@zeki.chat/ddp-client';
import { check } from 'meteor/check';
import { Meteor } from 'meteor/meteor';

import { afterLogoutCleanUpCallback } from '../lib/callbacks/afterLogoutCleanUpCallback';

declare module '@zeki.chat/ddp-client' {
	// eslint-disable-next-line @typescript-eslint/naming-convention
	interface ServerMethods {
		logoutCleanUp(user: IUser): Promise<void>;
	}
}

Meteor.methods<ServerMethods>({
	async logoutCleanUp(user) {
		check(user, Object);

		setImmediate(() => {
			void afterLogoutCleanUpCallback.run(user);
		});

		// App IPostUserLogout event hook
		await Apps.self?.triggerEvent(AppEvents.IPostUserLoggedOut, user);
	},
});
