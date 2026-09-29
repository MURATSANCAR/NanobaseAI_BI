import { Capabilities } from '@zeki.chat/capabilities';
import { Subscriptions, Users, LivechatContacts } from '@rocket.chat/models';
import { Meteor } from 'meteor/meteor';
import moment from 'moment';

import { getAppCount } from './lib/getAppCount';
import { settings } from '../../../../app/settings/server';

// Zeki: the internal license is installed in memory at boot. External licenses (setting, env var, cloud callbacks),
// license removal and cloud sync triggers are removed entirely — nothing here talks to any vendor service.
export const startLicense = async () => {
	Capabilities.setLicenseLimitCounter('activeUsers', () => Users.getActiveLocalUserCount());
	Capabilities.setLicenseLimitCounter('guestUsers', () => Users.getActiveLocalGuestCount());
	Capabilities.setLicenseLimitCounter('roomsPerGuest', async (context) =>
		context?.userId ? Subscriptions.countByUserIdExceptType(context.userId, 'd') : 0,
	);
	Capabilities.setLicenseLimitCounter('privateApps', () => getAppCount('private'));
	Capabilities.setLicenseLimitCounter('marketplaceApps', () => getAppCount('marketplace'));
	Capabilities.setLicenseLimitCounter('monthlyActiveContacts', () => LivechatContacts.countContactsOnPeriod(moment.utc().format('YYYY-MM')));

	return new Promise<void>((resolve) => {
		settings.onReady(() => {
			// Zeki: features react to the license with dynamic imports, which Meteor only allows once every
			// module has finished loading — so the internal license is applied from a startup hook.
			Meteor.startup(() => Capabilities.initialize());
			resolve();
		});
	});
};
