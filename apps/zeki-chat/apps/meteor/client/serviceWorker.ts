import { getRootUrlPathPrefix } from './lib/meteorRuntimeConfig';

const KEY = 'sw_last_reload';
const RELOAD_WINDOW = 1000 * 10;

function reload() {
	const lastReload = localStorage.getItem(KEY);

	if (lastReload) {
		const last = Date.parse(lastReload);

		if (!isNaN(last)) {
			const elapsed = Date.now() - last;

			if (elapsed < RELOAD_WINDOW) {
				return;
			}
		}
	}

	localStorage.setItem(KEY, new Date().toISOString());
	console.log('service worker: reloading to activate');
	window.location.reload();
}

if ('serviceWorker' in navigator) {
	const pathPrefix = getRootUrlPathPrefix().replace(/\/+$/, '');
	const scope = `${pathPrefix}/`;
	const scriptUrl = new URL(`${scope}enc.js`, window.location.origin).href;

	// skipWaiting/clients.claim activates updated restrictions for existing tabs.
	navigator.serviceWorker.addEventListener('controllerchange', () => {
		if (navigator.serviceWorker.controller?.scriptURL === scriptUrl) {
			reload();
		}
	});

	const install = async () => {
		const reg = await navigator.serviceWorker.register(scriptUrl, { scope, updateViaCache: 'none' });
		await reg.update();

		if (pathPrefix) {
			// Migrate only this application's former root enc.js registration.
			// Never unregister other portal workers or clear shared origin storage.
			const legacyUrl = new URL('/enc.js', window.location.origin).href;
			for (const previous of await navigator.serviceWorker.getRegistrations()) {
				const workers = [previous.active, previous.waiting, previous.installing].filter(Boolean);
				if (
					previous.scope === `${window.location.origin}/` &&
					workers.length > 0 &&
					workers.every((worker) => worker?.scriptURL === legacyUrl)
				) {
					await previous.unregister();
				}
			}
		}

		if (reg.active && navigator.serviceWorker.controller?.scriptURL !== scriptUrl) {
			reload();
		}
	};

	void install().catch((err) => {
		console.log('service worker registration failed:', err);
	});
}
