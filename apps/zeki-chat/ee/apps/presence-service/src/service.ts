import { api, getConnection, getTrashCollection } from '@zeki.chat/core-services';
import { registerServiceModels } from '@zeki.chat/models';
import { startBroker } from '@zeki.chat/network-broker';
import { startTracing } from '@zeki.chat/tracing';
import polka from 'polka';

const PORT = process.env.PORT || 3031;

void (async () => {
	const { db, client } = await getConnection();

	startTracing({ service: 'presence-service', db: client });

	registerServiceModels(db, await getTrashCollection());

	api.setBroker(startBroker());

	// need to import Presence service after models are registered
	const { Presence } = await import('@zeki.chat/presence');

	api.registerService(new Presence());

	await api.start();

	polka()
		.get('/health', async function (_req, res) {
			try {
				await api.nodeList();
				res.end('ok');
			} catch (err) {
				console.error('Service not healthy', err);

				res.writeHead(500);
				res.end('not healthy');
			}
		})
		.listen(PORT);
})();
