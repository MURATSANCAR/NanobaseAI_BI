import { Capabilities } from '@zeki.chat/capabilities';
import { Meteor } from 'meteor/meteor';
import { settings } from '../../../../app/settings/server';

export const startCapabilities = async () => new Promise<void>((resolve) => {
	settings.onReady(() => {
		Meteor.startup(() => Capabilities.initialize());
		resolve();
	});
});
