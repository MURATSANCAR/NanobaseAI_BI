import type { IZekiChatRecord } from '../IZekiChatRecord';

export interface IControl extends IZekiChatRecord {
	version: number;
	locked: boolean;
	hash?: string;
	buildAt?: string | Date;
	lockedAt?: string | Date;
}
