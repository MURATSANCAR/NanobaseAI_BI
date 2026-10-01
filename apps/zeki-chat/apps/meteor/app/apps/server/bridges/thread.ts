import type { IAppServerOrchestrator } from '@zeki.chat/apps';
import { ThreadBridge } from '@zeki.chat/apps/dist/server/bridges/ThreadBridge';
import type { IMessage } from '@zeki.chat/apps-engine/definition/messages';

export class AppThreadBridge extends ThreadBridge {
	constructor(private readonly orch: IAppServerOrchestrator) {
		super();
	}

	protected async getById(threadID: string, appId: string): Promise<IMessage[]> {
		this.orch.debugLog(`The App ${appId} is getting the thread: "${threadID}"`);

		return this.orch.getConverters()?.get('threads').convertById(threadID);
	}
}
