import { ZekiChatError } from './ZekiChatError';

export class PinMessagesNotAllowed extends ZekiChatError<'error-pinning-message'> {
	constructor(message = 'Pinning messages is not allowed', details?: unknown) {
		super('error-pinning-message', message, details);
	}
}
