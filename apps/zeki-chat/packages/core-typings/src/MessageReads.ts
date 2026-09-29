import type { IMessage } from './IMessage/IMessage';
import type { IZekiChatRecord } from './IZekiChatRecord';
import type { IUser } from './IUser';

// eslint-disable-next-line @typescript-eslint/naming-convention
export interface MessageReads extends IZekiChatRecord {
	tmid: IMessage['_id'];
	ls: Date;
	userId: IUser['_id'];
}
