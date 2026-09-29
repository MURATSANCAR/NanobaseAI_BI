import { SHA256 } from './sha256';

it.each([
	['meteor', '647d177cca8601046a3cb39e12f55bec5790bfcbc42199dd5fcf063200fac1d0'],
	['chat.example.invalid', '9f9fa4dbe0f6eec0623858630f03fb67a22b3f2882eb1b048f8294bbd391225e'],
])(`should hash %p as %p`, (input, expected) => {
	expect(SHA256(input)).toEqual(expected);
});
