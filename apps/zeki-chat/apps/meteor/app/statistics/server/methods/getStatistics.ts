import type { IStats } from '@zeki.chat/core-typings';
import type { ServerMethods } from '@zeki.chat/ddp-client';
import { Meteor } from 'meteor/meteor';

import { getLastStatistics } from '../functions/getLastStatistics';

declare module '@zeki.chat/ddp-client' {
	// eslint-disable-next-line @typescript-eslint/naming-convention
	interface ServerMethods {
		getStatistics(refresh?: boolean): IStats;
	}
}

Meteor.methods<ServerMethods>({
	async getStatistics(refresh) {
		const uid = Meteor.userId();
		if (!uid) {
			throw new Meteor.Error('error-invalid-user', 'Invalid user', { method: 'getStatistics' });
		}
		return getLastStatistics({
			userId: uid,
			refresh,
		});
	},
});
