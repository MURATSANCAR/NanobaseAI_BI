import type { IZekiChatRecord } from './IZekiChatRecord';

export interface IRole extends IZekiChatRecord {
	description: string;
	mandatory2fa?: boolean;
	name: string;
	protected: boolean;
	scope: 'Users' | 'Subscriptions';
}
