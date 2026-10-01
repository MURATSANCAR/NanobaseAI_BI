import { ZekiChatError } from './ZekiChatError';

export class InvalidCommandUsage extends ZekiChatError<'invalid-command-usage'> {
	constructor(message = 'Executing a command requires at least a message with a room id.', details?: string) {
		super('invalid-command-usage', message, details);
	}
}
