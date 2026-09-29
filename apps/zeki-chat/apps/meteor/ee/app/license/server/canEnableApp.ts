import type { IAppStorageItem } from '@rocket.chat/apps/dist/server/storage/IAppStorageItem';
import { Apps } from '@rocket.chat/core-services';
import type { CapabilityModule } from '@rocket.chat/core-typings';
import { Capabilities, type CapabilityRegistry } from '@zeki.chat/capabilities';

import { getInstallationSourceFromAppStorageItem } from '../../../../lib/apps/getInstallationSourceFromAppStorageItem';

type _canEnableAppDependencies = {
	Apps: typeof Apps;
	Capabilities: CapabilityRegistry;
};

export const _canEnableApp = async ({ Apps, Capabilities }: _canEnableAppDependencies, app: IAppStorageItem): Promise<void> => {
	if (!(await Apps.isInitialized())) {
		throw new Error('apps-engine-not-initialized');
	}

	// Migrated apps were installed before the validation was implemented
	// so they're always allowed to be enabled
	if (app.migrated) {
		return;
	}

	if (app.info.addon && !Capabilities.hasModule(app.info.addon as CapabilityModule)) {
		throw new Error('app-addon-not-valid');
	}

	const source = getInstallationSourceFromAppStorageItem(app);
	switch (source) {
		case 'private':
			if (await Capabilities.shouldPreventAction('privateApps')) {
				throw new Error('license-prevented');
			}

			break;
		default:
			if (await Capabilities.shouldPreventAction('marketplaceApps')) {
				throw new Error('license-prevented');
			}

			const marketplaceInfo = app.marketplaceInfo?.[0];
			if (marketplaceInfo?.isEnterpriseOnly && !Capabilities.isReady()) {
				throw new Error('invalid-license');
			}

			break;
	}
};

export const canEnableApp = async (app: IAppStorageItem): Promise<void> => _canEnableApp({ Apps, Capabilities }, app);
