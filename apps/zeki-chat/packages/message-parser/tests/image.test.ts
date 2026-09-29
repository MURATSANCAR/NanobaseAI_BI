import { parse } from '../src';
import { image, paragraph, plain } from './helpers';

test.each([
	[
		'![image](https://chat.example.invalid/assets/img/header/logo.svg)',
		[paragraph([image('https://chat.example.invalid/assets/img/header/logo.svg', plain('image'))])],
	],
	['![](https://chat.example.invalid/assets/img/header/logo.svg)', [paragraph([image('https://chat.example.invalid/assets/img/header/logo.svg')])]],
])('parses %p', (input, output) => {
	expect(parse(input)).toEqual(output);
});
