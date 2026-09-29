import type { IZekiChatRecord } from './IZekiChatRecord';

export interface IOAuthAuthCode extends IZekiChatRecord {
	authCode: string;
	clientId: string;
	userId: string;
	expires: Date;
	redirectUri: string;
}
