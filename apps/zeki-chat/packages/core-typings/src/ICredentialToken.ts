import type { IZekiChatRecord } from './IZekiChatRecord';

export interface ICredentialToken extends IZekiChatRecord {
	userInfo: {
		username?: string;
		attributes?: any;
		profile?: Record<string, any>;
	};
	expireAt: Date;
}
