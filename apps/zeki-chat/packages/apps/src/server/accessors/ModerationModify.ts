import type { IModerationModify } from '@zeki.chat/apps-engine/definition/accessors';
import type { IMessage } from '@zeki.chat/apps-engine/definition/messages';
import type { IUser } from '@zeki.chat/apps-engine/definition/users';

import type { ModerationBridge } from '../bridges';

export class ModerationModify implements IModerationModify {
	constructor(
		private moderationBridge: ModerationBridge,
		_appId: string,
	) {}

	public report(messageId: string, description: string, userId: string, appId: string): Promise<void> {
		return this.moderationBridge.doReport(messageId, description, userId, appId);
	}

	public dismissReportsByMessageId(messageId: IMessage['id'], reason: string, action: string, appId: string): Promise<void> {
		return this.moderationBridge.doDismissReportsByMessageId(messageId, reason, action, appId);
	}

	public dismissReportsByUserId(userId: IUser['id'], reason: string, action: string, appId: string): Promise<void> {
		return this.moderationBridge.doDismissReportsByUserId(userId, reason, action, appId);
	}
}
