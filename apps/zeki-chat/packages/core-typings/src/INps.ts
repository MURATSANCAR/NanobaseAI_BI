import type { IZekiChatRecord } from './IZekiChatRecord';
import type { IUser } from './IUser';

export enum NPSStatus {
	OPEN = 'open',
	SENDING = 'sending',
	SENT = 'sent',
	CLOSED = 'closed',
}

export interface INps extends IZekiChatRecord {
	startAt: Date; // start date a banner should be presented
	expireAt: Date; // date when banner should not be shown anymore
	createdBy: Pick<IUser, '_id' | 'username'>;
	createdAt: Date;
	status: NPSStatus;
}

export enum INpsVoteStatus {
	NEW = 'new',
	SENDING = 'sending',
	SENT = 'sent',
}

export interface INpsVote extends IZekiChatRecord {
	npsId: INps['_id'];
	ts: Date;
	identifier: string; // voter identifier
	roles?: IUser['roles']; // voter roles
	score: number;
	comment: string;
	status: INpsVoteStatus;
	sentAt?: Date;
}
