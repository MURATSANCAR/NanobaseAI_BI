import type { ICustomUserStatus } from '@zeki.chat/core-typings';
import type { ServerMethods } from '@zeki.chat/ddp-client';
import { CustomUserStatus } from '@zeki.chat/models';
import { Meteor } from 'meteor/meteor';

declare module '@zeki.chat/ddp-client' {
	// eslint-disable-next-line @typescript-eslint/naming-convention
	interface ServerMethods {
		listCustomUserStatus(): ICustomUserStatus[];
	}
}

Meteor.methods<ServerMethods>({
	async listCustomUserStatus() {
		const currentUserId = Meteor.userId();
		if (!currentUserId) {
			throw new Meteor.Error('error-invalid-user', 'Invalid user', {
				method: 'listCustomUserStatus',
			});
		}

		return CustomUserStatus.find({}).toArray();
	},
});
