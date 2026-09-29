import { ZekiChatError } from '../errors/ZekiChatError';

type CustomOAuthErrorDetails = {
	service?: string;
};

export class CustomOAuthError extends ZekiChatError<'custom-oauth-error', CustomOAuthErrorDetails> {
	constructor(reason?: string, details?: CustomOAuthErrorDetails) {
		super('custom-oauth-error', details?.service ? `${details.service}: ${reason}` : reason, details);
	}
}
