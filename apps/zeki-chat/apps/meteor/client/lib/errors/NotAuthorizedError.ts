import { ZekiChatError } from './ZekiChatError';

export class NotAuthorizedError extends ZekiChatError<'not-authorized'> {
	constructor(message = 'Not authorized', details?: unknown) {
		super('not-authorized', message, details);
	}
}
