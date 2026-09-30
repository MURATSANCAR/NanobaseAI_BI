import type { ZekiChatRecordDeleted } from '@zeki.chat/core-typings';
import type { Db, IndexDescription } from 'mongodb';

import { BaseRaw } from './BaseRaw';

export class TrashRaw extends BaseRaw<ZekiChatRecordDeleted<any>> {
	constructor(db: Db) {
		super(db, 'zeki__trash', undefined, {
			collectionNameResolver(name) {
				return name;
			},
		});
	}

	protected override modelIndexes(): IndexDescription[] | undefined {
		return [
			{ key: { __collection__: 1 } },
			{ key: { _deletedAt: 1 }, expireAfterSeconds: 60 * 60 * 24 * 30 },
			{ key: { rid: 1, __collection__: 1, _deletedAt: 1 } },
		];
	}
}
