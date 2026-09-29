import type { IZekiChatRecord } from './IZekiChatRecord';

export interface ILivechatAgentActivity extends IZekiChatRecord {
	agentId: string;
	date: number;
	lastStartedAt: Date;
	availableTime: number;
	serviceHistory: IServiceHistory[];
	lastStoppedAt?: Date;
}

export interface IServiceHistory {
	startedAt: Date;
	stoppedAt: Date;
}
