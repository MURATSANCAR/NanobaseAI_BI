import type { ICustomSound } from '@zeki.chat/core-typings';
import type { ServerMethods } from '@zeki.chat/ddp-client';
import { CustomSounds } from '@zeki.chat/models';
import { Meteor } from 'meteor/meteor';

declare module '@zeki.chat/ddp-client' {
	// eslint-disable-next-line @typescript-eslint/naming-convention
	interface ServerMethods {
		listCustomSounds(): ICustomSound[];
	}
}

Meteor.methods<ServerMethods>({
	async listCustomSounds() {
		return CustomSounds.find({}).toArray();
	},
});
