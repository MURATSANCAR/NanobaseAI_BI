import type { ISmarshHistory, ZekiChatRecordDeleted } from '@zeki.chat/core-typings';
import type { ISmarshHistoryModel } from '@zeki.chat/model-typings';
import type { Db, Collection } from 'mongodb';

import { BaseRaw } from './BaseRaw';

export class SmarshHistoryRaw extends BaseRaw<ISmarshHistory> implements ISmarshHistoryModel {
	constructor(db: Db, trash?: Collection<ZekiChatRecordDeleted<ISmarshHistory>>) {
		super(db, 'smarsh_history', trash);
	}
}
