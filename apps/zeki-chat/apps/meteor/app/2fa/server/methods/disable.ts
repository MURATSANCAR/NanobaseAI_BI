import type { ServerMethods } from '@zeki.chat/ddp-client';
import { Users } from '@zeki.chat/models';
import { Meteor } from 'meteor/meteor';

import { notifyOnUserChange } from '../../../lib/server/lib/notifyListener';
import { TOTP } from '../lib/totp';

declare module '@zeki.chat/ddp-client' {
	// eslint-disable-next-line @typescript-eslint/naming-convention
	interface ServerMethods {
		'2fa:disable': (code: string) => Promise<boolean>;
	}
}

Meteor.methods<ServerMethods>({
	async '2fa:disable'(code) {
		const userId = Meteor.userId();
		if (!userId) {
			throw new Meteor.Error('not-authorized');
		}

		const user = await Meteor.userAsync();

		if (!user) {
			throw new Meteor.Error('error-invalid-user', 'Invalid user', {
				method: '2fa:disable',
			});
		}

		if (!user.services?.totp?.enabled) {
			return false;
		}

		const verified = await TOTP.verify({
			secret: user.services.totp.secret,
			token: code,
			userId,
			backupTokens: user.services.totp.hashedBackup,
		});

		if (!verified) {
			return false;
		}

		const { modifiedCount } = await Users.disable2FAByUserId(userId);

		if (!modifiedCount) {
			return false;
		}

		void notifyOnUserChange({ clientAction: 'updated', id: user._id, diff: { 'services.totp.enabled': false } });

		return true;
	},
});
