import type { IZekiChatRecord } from './IZekiChatRecord';

export const DEFAULT_SLA_CONFIG = {
	ESTIMATED_WAITING_TIME_QUEUE: 9999999,
};

export interface IOmnichannelServiceLevelAgreements extends IZekiChatRecord {
	name: string;
	description?: string;
	dueTimeInMinutes: number;
}
