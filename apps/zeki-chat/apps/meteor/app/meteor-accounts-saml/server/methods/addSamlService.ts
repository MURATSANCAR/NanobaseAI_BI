import type { ServerMethods } from '@zeki.chat/ddp-client';
import { Meteor } from 'meteor/meteor';

import { addSamlService } from '../lib/settings';

declare module '@zeki.chat/ddp-client' {
	// eslint-disable-next-line @typescript-eslint/naming-convention
	interface ServerMethods {
		addSamlService(name: string): void;
	}
}

Meteor.methods<ServerMethods>({
	addSamlService(name) {
		addSamlService(name);
	},
});
