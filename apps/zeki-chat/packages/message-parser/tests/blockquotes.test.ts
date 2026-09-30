import { parse } from '../src';
import { paragraph, plain, quote, bold } from './helpers';

test.each([
	[
		`
As ZEKI AI CHAT said:
> meowww
> grr.
`.trim(),
		[paragraph([plain('As ZEKI AI CHAT said:')]), quote([paragraph([plain('meowww')]), paragraph([plain('grr.')])])],
	],
	[
		`
As ZEKI AI CHAT said:
> *meowww*
> grr.
`.trim(),
		[paragraph([plain('As ZEKI AI CHAT said:')]), quote([paragraph([bold([plain('meowww')])]), paragraph([plain('grr.')])])],
	],
	[
		`
As ZEKI AI CHAT said:
>meowww
>grr.
`.trim(),
		[paragraph([plain('As ZEKI AI CHAT said:')]), quote([paragraph([plain('meowww')]), paragraph([plain('grr.')])])],
	],
	[
		`
> meowww
>
> grr.
`.trim(),
		[quote([paragraph([plain('meowww')]), paragraph([plain('')]), paragraph([plain('grr.')])])],
	],
	[
		`
> meowww
> 
> grr.
`.trim(),
		[quote([paragraph([plain('meowww')]), paragraph([plain('')]), paragraph([plain('grr.')])])],
	],
])('parses %p', (input, output) => {
	expect(parse(input)).toEqual(output);
});
