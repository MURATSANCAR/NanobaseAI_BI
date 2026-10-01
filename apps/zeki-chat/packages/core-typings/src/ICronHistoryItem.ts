import type { IZekiChatRecord } from './IZekiChatRecord';

export interface ICronHistoryItem extends IZekiChatRecord {
	name: string;
	intendedAt: Date;
	startedAt: Date;
	finishedAt?: Date;
	result?: any;
	error?: any;
}
