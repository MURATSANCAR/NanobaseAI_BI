import type { IMessage } from './IMessage/IMessage';
import type { IZekiChatRecord } from './IZekiChatRecord';

export interface IReport extends IZekiChatRecord {
	message: IMessage;
	description: string;
	ts: Date;
	userId: string;
}
