import type { IWebdavAccount } from '@zeki.chat/core-typings';
import { WebdavAccounts } from '@zeki.chat/models';

export async function findWebdavAccountsByUserId({ uid }: { uid: string }): Promise<IWebdavAccount[]> {
	return WebdavAccounts.findWithUserId(uid, {
		projection: {
			_id: 1,
			username: 1,
			serverURL: 1,
			name: 1,
		},
	}).toArray();
}
