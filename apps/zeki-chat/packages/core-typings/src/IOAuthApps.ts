import type { IZekiChatRecord } from './IZekiChatRecord';

export interface IOAuthApps extends IZekiChatRecord {
	name: string;
	active: boolean;
	clientId: string;
	clientSecret?: string;
	redirectUri: string;
	_createdAt: Date;
	_createdBy: {
		_id: string;
		username: string;
	};
	appId?: string;
}
