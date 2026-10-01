import type { IZekiChatRecord } from './IZekiChatRecord';

export interface ILivechatUnitMonitor extends IZekiChatRecord {
	monitorId: string;
	unitId: string;
	username: string;
}
