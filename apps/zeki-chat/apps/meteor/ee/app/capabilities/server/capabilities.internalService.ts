import type { ICapabilities } from '@zeki.chat/core-services';
import { api, ServiceClassInternal } from '@zeki.chat/core-services';
import { Capabilities } from '@zeki.chat/capabilities';
import { guestPermissions } from '../../authorization/lib/guestPermissions';
import { resetEnterprisePermissions } from '../../authorization/server/resetEnterprisePermissions';

export class CapabilitiesService extends ServiceClassInternal implements ICapabilities {
	protected name = 'capabilities';
	constructor() {
		super();
		Capabilities.onReady(async () => {
			await api.broadcast('authorization.guestPermissions', guestPermissions);
			await resetEnterprisePermissions();
			await api.broadcast('capabilities.changed');
		});
	}
	override async started(): Promise<void> {
		if (!Capabilities.isReady()) return;
		await api.broadcast('authorization.guestPermissions', guestPermissions);
		await resetEnterprisePermissions();
	}
	hasModule(feature: string): boolean { return Capabilities.hasModule(feature); }
	isReady(): boolean { return Capabilities.isReady(); }
	getModules(): string[] { return Capabilities.getModules(); }
	getGuestPermissions(): string[] { return guestPermissions; }
}
