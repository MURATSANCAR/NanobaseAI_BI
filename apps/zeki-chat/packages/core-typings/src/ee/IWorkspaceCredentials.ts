import type { IZekiChatRecord } from '../IZekiChatRecord';

export interface IWorkspaceCredentials extends IZekiChatRecord {
	scope: string;
	expirationDate: Date;
	accessToken: string;
}
