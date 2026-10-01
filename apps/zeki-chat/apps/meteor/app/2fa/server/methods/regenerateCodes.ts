import type { ServerMethods } from '@zeki.chat/ddp-client';
import { Users } from '@zeki.chat/models';
import { Meteor } from 'meteor/meteor';

import { TOTP } from '../lib/totp';

declare module '@zeki.chat/ddp-client' {
	// eslint-disable-next-line @typescript-eslint/naming-convention
	interface ServerMethods {
		'2fa:regenerateCodes': (userToken: string) => { codes: string[] } | undefined;
	}
}

Meteor.methods<ServerMethods>({
	async '2fa:regenerateCodes'(userToken) {
		const userId = Meteor.userId();
		if (!userId) {
			throw new Meteor.Error('not-authorized');
		}

		const user = await Meteor.userAsync();
		if (!user) {
			throw new Meteor.Error('error-invalid-user', 'Invalid user', {
				method: '2fa:regenerateCodes',
			});
		}

		if (!user.services?.totp?.enabled) {
			throw new Meteor.Error('invalid-totp');
		}

		const verified = await TOTP.verify({
			secret: user.services.totp.secret,
			token: userToken,
			userId,
			backupTokens: user.services.totp.hashedBackup,
		});

		if (verified) {
			const { codes, hashedCodes } = TOTP.generateCodes();

			await Users.update2FABackupCodesByUserId(userId, hashedCodes);
			return { codes };
		}
	},
});
