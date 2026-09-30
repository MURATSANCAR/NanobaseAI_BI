import type { IZekiChatRecord } from './IZekiChatRecord';

export interface ILivechatTagRecord extends IZekiChatRecord {
	name: string;
	description: string;
	numDepartments: number;
	departments: Array<string>;
}
