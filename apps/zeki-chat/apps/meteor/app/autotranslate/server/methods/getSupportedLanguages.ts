import type { ISupportedLanguage } from '@zeki.chat/core-typings';
import type { ServerMethods } from '@zeki.chat/ddp-client';
import { DDPRateLimiter } from 'meteor/ddp-rate-limiter';
import { Meteor } from 'meteor/meteor';

import { getSupportedLanguages } from '../functions/getSupportedLanguages';

declare module '@zeki.chat/ddp-client' {
	// eslint-disable-next-line @typescript-eslint/naming-convention
	interface ServerMethods {
		'autoTranslate.getSupportedLanguages'(targetLanguage: string): ISupportedLanguage[] | undefined;
	}
}

Meteor.methods<ServerMethods>({
	async 'autoTranslate.getSupportedLanguages'(targetLanguage) {
		const userId = Meteor.userId();

		if (!userId) {
			throw new Meteor.Error('error-invalid-user', 'Invalid user', {
				method: 'getSupportedLanguages',
			});
		}

		return getSupportedLanguages(userId, targetLanguage);
	},
});

DDPRateLimiter.addRule(
	{
		type: 'method',
		name: 'autoTranslate.getSupportedLanguages',
		userId(/* userId*/) {
			return true;
		},
	},
	5,
	60000,
);
