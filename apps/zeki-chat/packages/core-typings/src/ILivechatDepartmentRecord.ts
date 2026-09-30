import type { IZekiChatRecord } from './IZekiChatRecord';

/** @deprecated */
export interface ILivechatDepartmentRecord extends IZekiChatRecord {
	name: string;
	enabled: boolean;
	description?: string;
	showOnRegistration: boolean;
	showOnOfflineForm: boolean;
	requestTagBeforeClosingChat?: boolean;
	email: string;
	chatClosingTags?: string[];
	offlineMessageChannelName: string;
	numAgents: number;
	businessHourId?: string;
	fallbackForwardDepartment?: string;
	departmentsAllowedToForward?: string[];
	// extra optional fields
	[k: string]: any;
}
