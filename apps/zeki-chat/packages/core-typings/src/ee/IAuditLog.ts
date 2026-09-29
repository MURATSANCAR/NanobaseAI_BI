import type { ILivechatAgent } from '../ILivechatAgent';
import type { ILivechatVisitor } from '../ILivechatVisitor';
import type { IMessage } from '../IMessage';
import type { IZekiChatRecord } from '../IZekiChatRecord';
import type { IRoom } from '../IRoom';
import type { IUser } from '../IUser';

export interface IAuditLog extends IZekiChatRecord {
	ts: Date;
	results: number;
	u: Pick<IUser, '_id' | 'username' | 'name' | 'avatarETag'>;
	fields: {
		type: string;
		msg: IMessage['msg'];
		startDate?: Date;
		endDate?: Date;
		rids?: IRoom['_id'][];
		room: IRoom['name'];
		users?: IUser['username'][];
		visitor?: ILivechatVisitor['_id'];
		agent?: ILivechatAgent['_id'];
		filters?: string;
	};
}
