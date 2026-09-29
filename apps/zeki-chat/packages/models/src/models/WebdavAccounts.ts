import type { IWebdavAccount, ZekiChatRecordDeleted } from '@zeki.chat/core-typings';
import type { IWebdavAccountsModel } from '@zeki.chat/model-typings';
import type { Collection, FindCursor, Db, DeleteResult, FindOptions, IndexDescription } from 'mongodb';

import { BaseRaw } from './BaseRaw';

export class WebdavAccountsRaw extends BaseRaw<IWebdavAccount> implements IWebdavAccountsModel {
	constructor(db: Db, trash?: Collection<ZekiChatRecordDeleted<IWebdavAccount>>) {
		super(db, 'webdav_accounts', trash);
	}

	protected override modelIndexes(): IndexDescription[] {
		return [{ key: { userId: 1 } }];
	}

	findOneByIdAndUserId(_id: string, userId: string, options: FindOptions<IWebdavAccount>): Promise<IWebdavAccount | null> {
		return this.findOne({ _id, userId }, options);
	}

	findOneByUserIdServerUrlAndUsername(
		{
			userId,
			serverURL,
			username,
		}: {
			userId: string;
			serverURL: string;
			username: string;
		},
		options: FindOptions<IWebdavAccount>,
	): Promise<IWebdavAccount | null> {
		return this.findOne({ userId, serverURL, username }, options);
	}

	findWithUserId(userId: string, options: FindOptions<IWebdavAccount>): FindCursor<IWebdavAccount> {
		const query = { userId };
		return this.find(query, options);
	}

	removeByUserAndId(_id: string, userId: string): Promise<DeleteResult> {
		return this.deleteOne({ _id, userId });
	}
}
