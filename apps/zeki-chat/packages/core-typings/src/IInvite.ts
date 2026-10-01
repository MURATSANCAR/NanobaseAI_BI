import type { IZekiChatRecord } from './IZekiChatRecord';

export interface IInvite extends IZekiChatRecord {
	days: number;
	maxUses: number;
	rid: string;
	userId: string;
	createdAt: Date;
	expires: Date | null;
	uses: number;
	url: string;
}
