import type { IZekiChatRecord } from './IZekiChatRecord';

export interface ILivechatDepartmentAgents extends IZekiChatRecord {
	departmentId: string;
	departmentEnabled: boolean;
	agentId: string;
	username: string;
	count: number;
	order: number;
}
