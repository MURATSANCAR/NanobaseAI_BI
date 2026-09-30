import type { IZekiChatRecord } from './IZekiChatRecord';

export interface IEmailMessageHistory extends IZekiChatRecord {
	email: string;
	createdAt?: Date;
}
