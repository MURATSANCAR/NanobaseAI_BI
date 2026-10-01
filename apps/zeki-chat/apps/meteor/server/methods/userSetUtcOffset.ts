import type { ServerMethods } from '@zeki.chat/ddp-client';
import { Users } from '@zeki.chat/models';
import { check } from 'meteor/check';
import { DDPRateLimiter } from 'meteor/ddp-rate-limiter';
import { Meteor } from 'meteor/meteor';

declare module '@zeki.chat/ddp-client' {
	// eslint-disable-next-line @typescript-eslint/naming-convention
	interface ServerMethods {
		userSetUtcOffset(utcOffset: number): void;
	}
}

Meteor.methods<ServerMethods>({
	async userSetUtcOffset(utcOffset) {
		check(utcOffset, Number);

		if (!this.userId) {
			return;
		}

		await Users.setUtcOffset(this.userId, utcOffset);
	},
});

DDPRateLimiter.addRule(
	{
		type: 'method',
		name: 'userSetUtcOffset',
		userId() {
			return true;
		},
	},
	1,
	60000,
);
