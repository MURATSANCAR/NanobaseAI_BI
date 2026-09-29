import { ZekiChatError } from './ZekiChatError';

export class InvalidUrlError extends ZekiChatError<'invalid-url'> {
	constructor(message = 'Invalid url', details?: string) {
		super('invalid-url', message, details);
	}
}
