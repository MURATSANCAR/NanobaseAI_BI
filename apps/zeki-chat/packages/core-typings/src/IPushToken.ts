import type { IZekiChatRecord } from './IZekiChatRecord';
import type { ILoginToken } from './IUser';

export const pushTokenTypes = ['gcm', 'apn'] as const;

export type IPushTokenTypes = (typeof pushTokenTypes)[number];

export interface IPushToken extends IZekiChatRecord {
	token: Partial<Record<IPushTokenTypes, string>>;
	appName: string;
	userId: string;
	enabled: boolean;
	authToken: ILoginToken['hashedToken'];
	metadata?: Record<string, unknown>;
	createdAt: Date;
	voipToken?: string;
}
