import { Capabilities } from '@zeki.chat/capabilities';

import { addSettings } from '../settings/deviceManagement';

let stopListening: (() => void) | undefined;
Capabilities.onToggledFeature('device-management', {
	up: async () => {
		const { createPermissions, createEmailTemplates } = await import('../lib/deviceManagement/startup');
		const { listenSessionLogin } = await import('../lib/deviceManagement/session');

		await addSettings();
		await createPermissions();
		await createEmailTemplates();
		stopListening = await listenSessionLogin();
	},
	down: async () => {
		stopListening?.();
		stopListening = undefined;
	},
});
