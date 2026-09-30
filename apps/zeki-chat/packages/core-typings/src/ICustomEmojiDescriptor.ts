import type { IZekiChatRecord } from './IZekiChatRecord';

export interface ICustomEmojiDescriptor extends IZekiChatRecord {
	name: string;
	aliases: string;
	extension: string;
}
