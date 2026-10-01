import type { ISetting } from '@zeki.chat/core-typings';
import type { ServerMethods } from '@zeki.chat/ddp-client';
import { Settings } from '@zeki.chat/models';
import { Meteor } from 'meteor/meteor';

declare module '@zeki.chat/ddp-client' {
	// eslint-disable-next-line @typescript-eslint/naming-convention
	interface ServerMethods {
		getSetupWizardParameters(): Promise<{
			settings: ISetting[];
			serverAlreadyRegistered: boolean;
		}>;
	}
}

Meteor.methods<ServerMethods>({
	async getSetupWizardParameters() {
		const setupWizardSettings = await Settings.findSetupWizardSettings().toArray();
		// Zeki: cloud registration does not exist; the wizard always skips the register step.
		const serverAlreadyRegistered = true;

		return {
			settings: setupWizardSettings,
			serverAlreadyRegistered,
		};
	},
});
