import type { IMessage, IReport, ZekiChatRecordDeleted } from '@zeki.chat/core-typings';
import type { IReportsModel } from '@zeki.chat/model-typings';
import type { Db, Collection } from 'mongodb';

import { BaseRaw } from './BaseRaw';

export class ReportsRaw extends BaseRaw<IReport> implements IReportsModel {
	constructor(db: Db, trash?: Collection<ZekiChatRecordDeleted<IReport>>) {
		super(db, 'reports', trash);
	}

	createWithMessageDescriptionAndUserId(message: IMessage, description: string, userId: string): ReturnType<BaseRaw<IReport>['insertOne']> {
		const record: Pick<IReport, 'message' | 'description' | 'ts' | 'userId'> = {
			message,
			description,
			ts: new Date(),
			userId,
		};
		return this.insertOne(record);
	}
}
