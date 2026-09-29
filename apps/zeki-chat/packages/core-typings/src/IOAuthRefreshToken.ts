import type { IZekiChatRecord } from './IZekiChatRecord';

export interface IOAuthRefreshToken extends IZekiChatRecord {
	refreshToken: string;
	expires?: Date;
	clientId: string;
	userId: string;
}
