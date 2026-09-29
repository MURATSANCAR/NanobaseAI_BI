import { Calendar } from '@rocket.chat/core-services';
import { Capabilities } from '@zeki.chat/capabilities';
import { Meteor } from 'meteor/meteor';

import { addSettings } from '../settings/outlookCalendar';

Meteor.startup(() =>
	Capabilities.whenFeature('outlook-calendar', async () => {
		addSettings();

		await Calendar.setupNextNotification();
		await Calendar.setupNextStatusChange();
	}),
);
