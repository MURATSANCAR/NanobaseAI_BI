import type { IZekiChatRecord } from './IZekiChatRecord';

export interface ILivechatTag extends IZekiChatRecord {
	name: string;
	description?: string;
	numDepartments: number;
	departments: Array<string>;
}

export type FindTagsResult = {
	tags: ILivechatTag[];
	count: number;
	offset: number;
	total: number;
};
