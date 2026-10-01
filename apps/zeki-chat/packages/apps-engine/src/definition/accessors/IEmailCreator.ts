import type { IEmail } from '../email';

export interface IEmailCreator {
	/**
	 * Sends an email through ZEKI AI CHAT
	 *
	 * @param email the email data
	 */
	send(email: IEmail): Promise<void>;
}
