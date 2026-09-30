import { ZekiChatError } from '../../../client/lib/errors/ZekiChatError';

export class UiKitTriggerTimeoutError extends ZekiChatError<'trigger-timeout'> {
	constructor(message = 'Timeout', details: { triggerId: string; appId: string }) {
		super('trigger-timeout', message, details);
	}
}
