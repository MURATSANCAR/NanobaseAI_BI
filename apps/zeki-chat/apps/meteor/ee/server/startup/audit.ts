import { Capabilities } from '@zeki.chat/capabilities';

import { createPermissions } from '../lib/audit/startup';

await Capabilities.whenFeature('auditing', async () => {
	await import('../lib/audit/methods');
	await import('../api/audit');

	await createPermissions();
});
