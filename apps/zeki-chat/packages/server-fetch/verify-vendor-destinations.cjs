// Run on the test server after building this package, never in the local workspace.
const assert = require('node:assert/strict');
const { assertNonVendorDestination } = require('./dist/checkVendorDestination');

const blocked = [
	'https://rocket.chat/',
	'https://cloud.rocket.chat/api',
	'https://a.b.rocket.chat/api',
	'https://CLOUD.ROCKET.CHAT.:443/api',
	'https://%63loud.rocket.chat/api',
	'https://user:password@cloud.rocket.chat/api',
	'https://rocketchat.github.io/',
	'https://rocketchat.atlassian.net/',
	'https://github.com/RocketChat/Rocket.Chat',
	'https://github.com/%52ocketChat/Rocket.Chat',
	'https://raw.githubusercontent.com/RocketChat/Rocket.Chat/main/package.json',
	'https://codeload.github.com/RocketChat/Rocket.Chat/zip/main',
	'https://api.github.com/repos/RocketChat/Rocket.Chat',
	'https://api.github.com/orgs/RocketChat',
];
const allowed = [
	'https://portal.nanobase.ai/timas/sohbet/',
	'http://127.0.0.1:4000/api/info',
	'https://github.com/MURATSANCAR/zeki-ai-chat',
	'https://api.github.com/repos/MURATSANCAR/zeki-ai-chat',
	'https://rocket.chat.example.org/',
	'https://example.org/rocket.chat',
];
for (const url of blocked) {
	assert.throws(() => assertNonVendorDestination(url), { message: 'error-vendor-destination-blocked' });
}
for (const url of allowed) {
	assert.doesNotThrow(() => assertNonVendorDestination(url));
}
console.log(JSON.stringify({ blockedCases: blocked.length, allowedCases: allowed.length, status: 'PASS' }));
