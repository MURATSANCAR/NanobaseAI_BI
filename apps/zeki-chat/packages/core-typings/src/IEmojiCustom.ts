import type { IZekiChatRecord } from './IZekiChatRecord';

export interface IEmojiCustom extends IZekiChatRecord {
	name: string;
	aliases: string[];
	extension: string;
	etag?: string;
}
