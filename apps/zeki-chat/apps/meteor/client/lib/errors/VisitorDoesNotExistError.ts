import { ZekiChatError } from './ZekiChatError';

export class VisitorDoesNotExistError extends ZekiChatError<'visitor-does-not-exist'> {
	constructor(message = 'Visitor does not exist', details?: string) {
		super('visitor-does-not-exist', message, details);
	}
}
