import type { ILivechatDepartment } from './ILivechatDepartment';
import type { IZekiChatRecord } from './IZekiChatRecord';
import type { IUser } from './IUser';

export interface IOmnichannelCannedResponse extends IZekiChatRecord {
	shortcut: string;
	text: string;
	scope: string;
	tags: string[];
	// userId is optional, its only required when scope === 'user'
	userId?: IUser['_id'];
	departmentId?: ILivechatDepartment['_id'];
	createdBy: {
		_id: IUser['_id'];
		username: string;
	};
	_createdAt: Date;
}
