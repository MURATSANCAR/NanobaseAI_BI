import type { IOutgoingIntegration } from '@zeki.chat/core-typings';
import { Integrations } from '@zeki.chat/models';
import { Meteor } from 'meteor/meteor';

import { triggerHandler } from './lib/triggerHandler';

Meteor.startup(async () => {
	await Integrations.find<IOutgoingIntegration>({ type: 'webhook-outgoing' }).forEach((data) =>
		triggerHandler.addIntegration(data as IOutgoingIntegration),
	);
});
