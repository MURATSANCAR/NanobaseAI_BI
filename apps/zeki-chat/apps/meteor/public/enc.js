self.addEventListener('install', function (event) {
	event.waitUntil(self.skipWaiting()); // Activate worker immediately
});

self.addEventListener('activate', function (event) {
	event.waitUntil(self.clients.claim()); // Become available to all pages
});

function base64Decode(string) {
	string = atob(string);
	const length = string.length,
		buf = new ArrayBuffer(length),
		bufView = new Uint8Array(buf);
	for (var i = 0; i < string.length; i++) {
		bufView[i] = string.charCodeAt(i);
	}
	return buf;
}

function base64DecodeString(string) {
	return atob(string);
}

const decrypt = async (key, iv, file) => {
	const ivArray = base64Decode(iv);
	const cryptoKey = await crypto.subtle.importKey('jwk', key, { name: 'AES-CTR' }, true, ['encrypt', 'decrypt']);
	const result = await crypto.subtle.decrypt({ name: 'AES-CTR', counter: ivArray, length: 64 }, cryptoKey, file);

	return result;
};

// File decryption must never use the worker to bypass the page's network policy.
const requireLocalUrl = (input) => {
	const parsed = new URL(input, self.location.origin);
	if (parsed.origin !== self.location.origin || parsed.username || parsed.password) {
		throw new Error('External file decryption URLs are disabled');
	}
	return parsed.href;
};

const getUrlParams = (url) => {
	const urlObj = new URL(requireLocalUrl(url));

	const rawKey = urlObj.searchParams.get('key');
	if (!rawKey) {
		throw new Error('Missing "key" query param');
	}


	const k = base64DecodeString(decodeURIComponent(rawKey));

	urlObj.searchParams.delete('key');

	const { key, iv, name, type } = JSON.parse(k);

	const newUrl = urlObj.href.replace('/file-decrypt/', '/');

	return { key, iv, url: newUrl, name, type };
};

// Decrypted documents must not inherit a cached or upstream document policy.
const restrictiveResponse = (body, { status = 200, statusText = '', headers } = {}) => {
	const protectedHeaders = new Headers(headers);
	protectedHeaders.set(
		'Content-Security-Policy',
		"sandbox; default-src 'none'; img-src data: blob:; media-src data: blob:; style-src 'unsafe-inline'; frame-src 'none'; connect-src 'none'; base-uri 'none'; form-action 'none'",
	);
	protectedHeaders.set('X-Content-Type-Options', 'nosniff');
	protectedHeaders.set('Cache-Control', 'no-store');
	return new Response(body, { status, statusText, headers: protectedHeaders });
};

self.addEventListener('fetch', (event) => {
	if (!event.request.url.includes('/file-decrypt/')) {
		return;
	}

	event.respondWith(
		(async () => {
			try {
				const { url, key, iv, name, type } = getUrlParams(event.request.url);
				const res = await fetch(requireLocalUrl(url), {
					mode: 'same-origin',
					redirect: 'error',
					cache: 'no-store',
				});
				if (res.status !== 200) {
					return restrictiveResponse(res.body, { status: res.status, statusText: res.statusText, headers: res.headers });
				}

				const file = await res.arrayBuffer();
				if (file.byteLength === 0) {
					return restrictiveResponse(file, { status: res.status, statusText: res.statusText, headers: res.headers });
				}

				const result = await decrypt(key, iv, file);
				const headers = new Headers(res.headers);
				headers.set('Content-Disposition', 'inline; filename="' + name + '"');
				headers.set('Content-Type', type);
				return restrictiveResponse(result, { status: res.status, statusText: res.statusText, headers });
			} catch {
				return restrictiveResponse('File decryption failed', {
					status: 400,
					headers: { 'Content-Type': 'text/plain; charset=utf-8' },
				});
			}
		})(),
	);
});

self.addEventListener('message', async (event) => {
	if (event.data.type !== 'attachment-download') {
		return;
	}

	const { url, key, iv } = getUrlParams(event.data.url);
	const res = await fetch(requireLocalUrl(url), { mode: 'same-origin', redirect: 'error', cache: 'no-store' });

	const file = await res.arrayBuffer();
	const result = await decrypt(key, iv, file);
	event.source.postMessage({
		id: event.data.id,
		type: 'attachment-download-result',
		result,
	});
	// .catch((error) => {
	// 	console.error('Posting message failed:', error);
	// 	event.source.postMessage({
	// 		id: event.data.id,
	// 		type: 'attachment-download-result',
	// 		error,
	// 	});
	// });
});
