import { Capabilities } from '@zeki.chat/capabilities';
import { isDepartmentCreationAvailable } from '@rocket.chat/omni-core';

export function isDepartmentCreationAvailablePatch(): void {
	isDepartmentCreationAvailable.patch(async (next) => {
		// Skip the standard check when Livechat Enterprise is enabled, as it allows unlimited departments
		if (Capabilities.hasModule('livechat-enterprise')) {
			return true;
		}

		return next();
	});
}
