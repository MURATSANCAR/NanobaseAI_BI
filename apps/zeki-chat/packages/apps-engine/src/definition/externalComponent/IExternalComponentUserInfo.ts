import type { IUser } from '../users';

type ClientUserInfo = Pick<IUser, 'id' | 'username'>;

/**
 * Represents the user's information returned to
 * the external component.
 */
export interface IExternalComponentUserInfo extends ClientUserInfo {
	/**
	 * the avatar URL of the ZEKI AI CHAT user
	 */
	avatarUrl: string;
}
