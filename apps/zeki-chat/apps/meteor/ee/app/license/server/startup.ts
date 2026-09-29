import { License } from '@rocket.chat/license';
import { Subscriptions, Users, LivechatContacts } from '@rocket.chat/models';
import { Meteor } from 'meteor/meteor';
import moment from 'moment';

import { getAppCount } from './lib/getAppCount';
import { settings } from '../../../../app/settings/server';

// Zeki: the internal license is installed in memory at boot. External licenses (setting, env var, cloud callbacks),
// license removal and cloud sync triggers are removed entirely — nothing here talks to any vendor service.
export const startLicense = async () => {
	License.setLicenseLimitCounter('activeUsers', () => Users.getActiveLocalUserCount());
	License.setLicenseLimitCounter('guestUsers', () => Users.getActiveLocalGuestCount());
	License.setLicenseLimitCounter('roomsPerGuest', async (context) =>
		context?.userId ? Subscriptions.countByUserIdExceptType(context.userId, 'd') : 0,
	);
	License.setLicenseLimitCounter('privateApps', () => getAppCount('private'));
	License.setLicenseLimitCounter('marketplaceApps', () => getAppCount('marketplace'));
	License.setLicenseLimitCounter('monthlyActiveContacts', () => LivechatContacts.countContactsOnPeriod(moment.utc().format('YYYY-MM')));

	return new Promise<void>((resolve) => {
		settings.onReady(() => {
			// Zeki: features react to the license with dynamic imports, which Meteor only allows once every
			// module has finished loading — so the internal license is applied from a startup hook.
			Meteor.startup(() => License.applyInternalLicense());
			resolve();
		});
	});
};
