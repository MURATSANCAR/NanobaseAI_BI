import type { IAppServerOrchestrator } from '@zeki.chat/apps';
import { UiInteractionBridge as AppsEngineUiInteractionBridge } from '@zeki.chat/apps/dist/server/bridges/UiInteractionBridge';
import type { IUIKitInteraction } from '@zeki.chat/apps-engine/definition/uikit';
import type { IUser } from '@zeki.chat/apps-engine/definition/users';
import { api } from '@zeki.chat/core-services';
import type * as UiKit from '@zeki.chat/ui-kit';

export class UiInteractionBridge extends AppsEngineUiInteractionBridge {
	constructor(private readonly orch: IAppServerOrchestrator) {
		super();
	}

	protected async notifyUser(user: IUser, interaction: IUIKitInteraction, appId: string): Promise<void> {
		this.orch.debugLog(`The App ${appId} is sending an interaction to user.`);

		const app = this.orch.getManager()?.getOneById(appId);

		if (!app) {
			throw new Error('Invalid app provided');
		}

		void api.broadcast('notify.uiInteraction', user.id, interaction as UiKit.ServerInteraction);
	}
}
