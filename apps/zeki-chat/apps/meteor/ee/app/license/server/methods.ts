import type { ILicenseTag, CapabilityModule } from '@rocket.chat/core-typings';
import type { ServerMethods } from '@rocket.chat/ddp-client';
import { Capabilities } from '@zeki.chat/capabilities';
import { check } from 'meteor/check';
import { Meteor } from 'meteor/meteor';

declare module '@rocket.chat/ddp-client' {
	// eslint-disable-next-line @typescript-eslint/naming-convention
	interface ServerMethods {
		'license:hasLicense'(feature: string): boolean;
		'license:getModules'(): string[];
		'license:getTags'(): ILicenseTag[];
		'license:isEnterprise'(): boolean;
	}
}

Meteor.methods<ServerMethods>({
	'license:hasLicense'(feature: string) {
		check(feature, String);

		return Capabilities.hasModule(feature as CapabilityModule);
	},
	'license:getModules'() {
		return Capabilities.getModules();
	},
	'license:getTags'() {
		return Capabilities.getTags();
	},
	'license:isEnterprise'() {
		return Capabilities.isReady();
	},
});
