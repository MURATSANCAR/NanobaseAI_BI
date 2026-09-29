import { Capabilities } from '@zeki.chat/capabilities';

await Capabilities.whenFeature('message-read-receipt', async () => {
	await import('./hooks');
});
