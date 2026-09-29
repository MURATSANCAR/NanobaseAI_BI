import type { IAppServerOrchestrator } from '@zeki.chat/apps';
import { ModerationBridge } from '@zeki.chat/apps/dist/server/bridges/ModerationBridge';
import type { IMessage } from '@zeki.chat/apps-engine/definition/messages';
import type { IUser } from '@zeki.chat/apps-engine/definition/users';
import { ModerationReports } from '@zeki.chat/models';

import { reportMessage } from '../../../../server/lib/moderation/reportMessage';

export class AppModerationBridge extends ModerationBridge {
	constructor(private readonly orch: IAppServerOrchestrator) {
		super();
	}

	protected async report(messageId: IMessage['id'], description: string, userId: string, appId: string): Promise<void> {
		this.orch.debugLog(`The App ${appId} is creating a new report.`);

		if (!messageId) {
			throw new Error('Invalid message id');
		}

		if (!description) {
			throw new Error('Invalid description');
		}

		await reportMessage(messageId, description, userId || 'zeki.bot');
	}

	protected async dismissReportsByMessageId(messageId: IMessage['id'], reason: string, action: string, appId: string): Promise<void> {
		this.orch.debugLog(`The App ${appId} is dismissing reports by message id.`);

		if (!messageId) {
			throw new Error('Invalid message id');
		}

		await ModerationReports.hideMessageReportsByMessageId(messageId, appId, reason, action);
	}

	protected async dismissReportsByUserId(userId: IUser['id'], reason: string, action: string, appId: string): Promise<void> {
		this.orch.debugLog(`The App ${appId} is dismissing reports by user id.`);

		if (!userId) {
			throw new Error('Invalid user id');
		}
		await ModerationReports.hideMessageReportsByUserId(userId, appId, reason, action);
	}
}
