import type { ILivechatTrigger, ZekiChatRecordDeleted } from '@zeki.chat/core-typings';
import type { ILivechatTriggerModel } from '@zeki.chat/model-typings';
import type { Collection, FindCursor, Db, IndexDescription, UpdateFilter, UpdateResult } from 'mongodb';

import { BaseRaw } from './BaseRaw';

export class LivechatTriggerRaw extends BaseRaw<ILivechatTrigger> implements ILivechatTriggerModel {
	constructor(db: Db, trash?: Collection<ZekiChatRecordDeleted<ILivechatTrigger>>) {
		super(db, 'livechat_trigger', trash);
	}

	protected override modelIndexes(): IndexDescription[] {
		return [{ key: { enabled: 1 } }];
	}

	findEnabled(): FindCursor<ILivechatTrigger> {
		return this.find({ enabled: true });
	}

	updateById(_id: string, data: Omit<ILivechatTrigger, '_id' | '_updatedAt'>): Promise<UpdateResult> {
		return this.updateOne({ _id }, { $set: data } as UpdateFilter<ILivechatTrigger>); // TODO: remove this cast when TypeScript is updated
	}
}
