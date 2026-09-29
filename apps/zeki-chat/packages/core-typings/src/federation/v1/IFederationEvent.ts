import type { IZekiChatRecord } from '../../IZekiChatRecord';

export interface IFederationEvent extends IZekiChatRecord {
	origin: string;
	context: { roomId: string };
	parentIds: string[];
	type: string;
	timestamp: Date;
	data: any;
	hasChildren: boolean;
}
