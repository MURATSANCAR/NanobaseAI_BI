import type { Credentials } from '@zeki.chat/api-client';
import type { IUser } from '@zeki.chat/core-typings';

export const password = 'R0ck3t.ch@tP@ssw0rd1234.!';
export const adminUsername = 'zekichat.internal.admin.test';
export const adminEmail = `${adminUsername}@rocket.chat`;
export const adminPassword = adminUsername;

export type IUserWithCredentials = {
	user: IUser;
	credentials: Credentials;
};
