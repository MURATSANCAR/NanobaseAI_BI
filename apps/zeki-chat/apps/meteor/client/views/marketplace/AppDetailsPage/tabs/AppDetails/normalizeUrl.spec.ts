import { it } from '@jest/globals';

import { normalizeUrl } from './normalizeUrl';

it.each([
	['https://chat.example.invalid', 'https://chat.example.invalid'],
	['//chat.example.invalid', 'https://chat.example.invalid'],
	['chat.example.invalid', 'https://chat.example.invalid'],
	['examplechat@chat.example.invalid', 'mailto:examplechat@chat.example.invalid'],
	['plain_text', undefined],
])('should normalize %o as %o', (input, output) => {
	expect(normalizeUrl(input)).toBe(output);
});
