import type { ServerMethods } from '@zeki.chat/ddp-client';
import { Capabilities } from '@zeki.chat/capabilities';
import { check } from 'meteor/check';
import { Meteor } from 'meteor/meteor';

declare module '@zeki.chat/ddp-client' {
	interface ServerMethods {
		'capabilities:hasModule'(feature: string): boolean;
		'capabilities:getModules'(): string[];
	}
}
Meteor.methods<ServerMethods>({
	'capabilities:hasModule'(feature: string) { check(feature, String); return Capabilities.hasModule(feature); },
	'capabilities:getModules'() { return Capabilities.getModules(); },
});
