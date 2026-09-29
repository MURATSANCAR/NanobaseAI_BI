import type { IAppServerOrchestrator } from '@zeki.chat/apps';
import { ExperimentalBridge } from '@zeki.chat/apps/dist/server/bridges/ExperimentalBridge';

export class AppExperimentalBridge extends ExperimentalBridge {
	constructor(protected readonly orch: IAppServerOrchestrator) {
		super();
	}
}
