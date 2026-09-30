import type { IAppServerOrchestrator } from '@zeki.chat/apps';
import { AppDetailChangesBridge as DetailChangesBridge } from '@zeki.chat/apps/dist/server/bridges/AppDetailChangesBridge';
import type { ISetting } from '@zeki.chat/apps-engine/definition/settings';

export class AppDetailChangesBridge extends DetailChangesBridge {
	constructor(private readonly orch: IAppServerOrchestrator) {
		super();
	}

	protected onAppSettingsChange(appId: string, setting: ISetting): void {
		const logFailure = () => console.warn('failed to notify about the setting change.', appId);

		try {
			this.orch.getNotifier().appSettingsChange(appId, setting).catch(logFailure);
		} catch (e) {
			logFailure();
		}
	}
}
