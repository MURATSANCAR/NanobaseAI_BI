import type { ICapabilities } from '@rocket.chat/core-services';
import { api, ServiceClassInternal } from '@rocket.chat/core-services';
import type { CapabilityModule } from '@rocket.chat/core-typings';
import { Capabilities } from '@zeki.chat/capabilities';

import { guestPermissions } from '../../authorization/lib/guestPermissions';
import { resetEnterprisePermissions } from '../../authorization/server/resetEnterprisePermissions';

export class LicenseService extends ServiceClassInternal implements ICapabilities {
	protected name = 'license';

	constructor() {
		super();

		Capabilities.onReady((): void => {
			if (!Capabilities.isReady()) {
				return;
			}

			void api.broadcast('authorization.guestPermissions', guestPermissions);
			void resetEnterprisePermissions();
		});

		Capabilities.onModule((licenseModule) => {
			void api.broadcast('license.module', licenseModule);
		});

		this.onEvent('license.actions', (preventedActions) => Capabilities.syncShouldPreventActionResults(preventedActions));
	}

	override async started(): Promise<void> {
		if (!Capabilities.isReady()) {
			return;
		}

		void api.broadcast('authorization.guestPermissions', guestPermissions);
		await resetEnterprisePermissions();
	}

	hasModule(feature: CapabilityModule): boolean {
		return Capabilities.hasModule(feature);
	}

	hasValidLicense(): boolean {
		return Capabilities.isReady();
	}

	getModules(): string[] {
		return Capabilities.getModules();
	}

	getGuestPermissions(): string[] {
		return guestPermissions;
	}
}
