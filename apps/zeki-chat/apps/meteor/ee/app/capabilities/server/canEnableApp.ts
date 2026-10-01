import type { IAppStorageItem } from '@zeki.chat/apps/dist/server/storage/IAppStorageItem';
import { Apps } from '@zeki.chat/core-services';
import { Capabilities, type CapabilityRegistry } from '@zeki.chat/capabilities';
import { getInstallationSourceFromAppStorageItem } from '../../../../lib/apps/getInstallationSourceFromAppStorageItem';

type Dependencies = { Apps: typeof Apps; Capabilities: CapabilityRegistry };
export const _canEnableApp = async ({ Apps, Capabilities }: Dependencies, app: IAppStorageItem): Promise<void> => {
	if (!(await Apps.isInitialized())) throw new Error('apps-engine-not-initialized');
	// First-party capabilities are not third-party marketplace entitlements.
	if (getInstallationSourceFromAppStorageItem(app) !== 'private') throw new Error('marketplace-unavailable');
	if (app.info.addon && !Capabilities.hasModule(app.info.addon)) throw new Error('app-addon-not-available');
};
export const canEnableApp = async (app: IAppStorageItem): Promise<void> => _canEnableApp({ Apps, Capabilities }, app);
