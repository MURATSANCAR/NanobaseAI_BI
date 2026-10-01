import { ZekiChatError } from './ZekiChatError';

export class InvalidPreview extends ZekiChatError<'error-invalid-preview'> {
	constructor(message = 'Preview Item must have an id, type, and value.', details?: string) {
		super('error-invalid-preview', message, details);
	}
}
