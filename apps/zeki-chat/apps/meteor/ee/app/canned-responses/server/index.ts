import { Capabilities } from '@zeki.chat/capabilities';

await Capabilities.whenFeature('canned-responses', async () => {
	const { createSettings } = await import('./settings');
	await import('./permissions');
	await import('./hooks/onRemoveAgentDepartment');
	await import('./hooks/onSaveAgentDepartment');
	await import('./hooks/cannedResponses');
	await import('./methods/saveCannedResponse');
	await import('./methods/removeCannedResponse');

	await createSettings();
});
