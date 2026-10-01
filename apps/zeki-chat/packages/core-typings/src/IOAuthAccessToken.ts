import type { IZekiChatRecord } from './IZekiChatRecord';

export interface IOAuthAccessToken extends IZekiChatRecord {
	accessToken: string;
	expires?: Date;
	clientId: string;
	userId: string;
	refreshToken?: string;
	refreshTokenExpiresAt?: Date;
}
