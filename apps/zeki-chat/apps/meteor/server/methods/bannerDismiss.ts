import type { ServerMethods } from '@zeki.chat/ddp-client';
import { Users } from '@zeki.chat/models';
import { Meteor } from 'meteor/meteor';

import { notifyOnUserChange } from '../../app/lib/server/lib/notifyListener';

declare module '@zeki.chat/ddp-client' {
	// eslint-disable-next-line @typescript-eslint/naming-convention
	interface ServerMethods {
		'banner/dismiss'({ id }: { id: string }): void;
	}
}

Meteor.methods<ServerMethods>({
	async 'banner/dismiss'({ id }) {
		const userId = Meteor.userId();
		if (!userId) {
			throw new Meteor.Error('error-invalid-user', 'Invalid user', { method: 'banner/dismiss' });
		}

		await Users.setBannerReadById(userId, id);

		void notifyOnUserChange({
			id: userId,
			clientAction: 'updated',
			diff: {
				[`banners.${id}.read`]: true,
			},
		});
	},
});
