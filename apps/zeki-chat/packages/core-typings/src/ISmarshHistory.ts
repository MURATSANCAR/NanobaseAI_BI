import type { IZekiChatRecord } from './IZekiChatRecord';

export interface ISmarshHistory extends IZekiChatRecord {
	lastRan: Date;
	lastResult: string;
}
