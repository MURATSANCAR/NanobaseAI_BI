import type { IZekiChatRecord } from './IZekiChatRecord';

export interface ICustomSound extends IZekiChatRecord {
	name: string;
	extension: string;
	src?: string;
	random?: unknown;
}
