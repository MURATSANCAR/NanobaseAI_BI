import { parse } from '../src';
import { lineBreak, paragraph, plain, link } from './helpers';
import { autoLink } from '../src/utils';

test.each([
	[
		'https://pt.wikipedia.org/wiki/Condi%C3%A7%C3%A3o_de_corrida#:~:text=Uma%20condi%C3%A7%C3%A3o%20de%20corrida%20%C3%A9,sequ%C3%AAncia%20ou%20sincronia%20doutros%20eventos',
		[
			paragraph([
				link(
					'https://pt.wikipedia.org/wiki/Condi%C3%A7%C3%A3o_de_corrida#:~:text=Uma%20condi%C3%A7%C3%A3o%20de%20corrida%20%C3%A9,sequ%C3%AAncia%20ou%20sincronia%20doutros%20eventos',
				),
			]),
		],
	],
	['https://pt.wikipedia.org/', [paragraph([link('https://pt.wikipedia.org/')])]],
	['https://pt.wikipedia.org/with-hyphen', [paragraph([link('https://pt.wikipedia.org/with-hyphen')])]],
	['https://pt.wikipedia.org/with_underscore', [paragraph([link('https://pt.wikipedia.org/with_underscore')])]],
	[
		'https://www.npmjs.com/package/@zeki.chat/message-parser',
		[paragraph([link('https://www.npmjs.com/package/@zeki.chat/message-parser')])],
	],
	['http:/chat.example.invalid/teste', [paragraph([plain('http:/chat.example.invalid/teste')])]],
	['https:/chat.example.invalid/', [paragraph([plain('https:/chat.example.invalid/')])]],
	['https://test', [paragraph([plain('https://test')])]],
	['httpsss://chat.example.invalid/test', [paragraph([link('httpsss://chat.example.invalid/test')])]],
	['https://chat.example.invalid/test', [paragraph([link('https://chat.example.invalid/test')])]],
	['https://chat.example.invalid', [paragraph([link('https://chat.example.invalid')])]],
	['https://chat.example.invalid/test', [paragraph([link('https://chat.example.invalid/test')])]],
	['https://chat.example.invalid/test?search', [paragraph([link('https://chat.example.invalid/test?search')])]],
	['https://chat.example.invalid/test?search=test', [paragraph([link('https://chat.example.invalid/test?search=test')])]],
	['https://chat.example.invalid', [paragraph([link('https://chat.example.invalid')])]],
	['http://127.0.0.1:3000/images/logo/logo.png', [paragraph([link('http://127.0.0.1:3000/images/logo/logo.png')])]],
	['https://localhost', [paragraph([link('https://localhost')])]],
	['https://localhost:3000', [paragraph([link('https://localhost:3000')])]],
	['https://localhost:3000#fragment', [paragraph([link('https://localhost:3000#fragment')])]],
	['https://localhost:3000#', [paragraph([link('https://localhost:3000#')])]],
	['https://localhost:3000?', [paragraph([link('https://localhost:3000?')])]],
	['https://localhost:3000/', [paragraph([link('https://localhost:3000/')])]],
	['ftp://user:pass@localhost:21/etc/hosts', [paragraph([link('ftp://user:pass@localhost:21/etc/hosts')])]],
	['ssh://test@example.com', [paragraph([link('ssh://test@example.com')])]],
	['custom://test@example.com', [paragraph([link('custom://test@example.com')])]],
	['ftp://example.com', [paragraph([link('ftp://example.com')])]],
	['https://www.thingiverse.com/thing:5451684', [paragraph([link('https://www.thingiverse.com/thing:5451684')])]],
	['http://📙.la/❤️', [paragraph([link('http://📙.la/❤️')])]],
	[
		'https://chat.example.invalid/reference/api/rest-api#production-security-concerns look at this',
		[paragraph([link('https://chat.example.invalid/reference/api/rest-api#production-security-concerns'), plain(' look at this')])],
	],
	[
		'https://chat.example.invalid/reference/api/rest-api look at this',
		[paragraph([link('https://chat.example.invalid/reference/api/rest-api'), plain(' look at this')])],
	],

	[
		'https://chat.example.invalid/reference/api/rest-api#fragment?query=query look at this',
		[paragraph([link('https://chat.example.invalid/reference/api/rest-api#fragment?query=query'), plain(' look at this')])],
	],
	['https://chat.example.invalid look at this', [paragraph([link('https://chat.example.invalid'), plain(' look at this')])]],
	[
		'https://chat.example.invalid?query=query look at this',
		[paragraph([link('https://chat.example.invalid?query=query'), plain(' look at this')])],
	],
	[
		'https://chat.example.invalid?query=query\nline break',
		[paragraph([link('https://chat.example.invalid?query=query')]), paragraph([plain('line break')])],
	],
	[
		'https://chat.example.invalid?query=query\n\nline break',
		[paragraph([link('https://chat.example.invalid?query=query')]), lineBreak(), paragraph([plain('line break')])],
	],
	[
		'https://chat.example.invalid?query=query_with_underscore look at this',
		[paragraph([link('https://chat.example.invalid?query=query_with_underscore'), plain(' look at this')])],
	],
	[
		'https://chat.example.invalid/path_with_underscore look at this',
		[paragraph([link('https://chat.example.invalid/path_with_underscore'), plain(' look at this')])],
	],
	[
		'https://chat.example.invalid#fragment_with_underscore look at this',
		[paragraph([link('https://chat.example.invalid#fragment_with_underscore'), plain(' look at this')])],
	],
	['https://chat.example.invalid followed by text', [paragraph([link('https://chat.example.invalid'), plain(' followed by text')])]],
	[
		'two urls https://chat.example.invalid , https://chat.example.invalid',
		[paragraph([plain('two urls '), link('https://chat.example.invalid'), plain(' , '), link('https://chat.example.invalid')])],
	],
	['https://chat.example.invalid', [paragraph([link('https://chat.example.invalid')])]],
	['https://en.m.wikipedia.org/wiki/Main_Page', [paragraph([link('https://en.m.wikipedia.org/wiki/Main_Page')])]],
	['test.1test.com', [paragraph([link('//test.1test.com', [plain('test.1test.com')])])]],
	['http://test.e-xample.com', [paragraph([link('http://test.e-xample.com')])]],
	['www.n-tv.de', [paragraph([link('//www.n-tv.de', [plain('www.n-tv.de')])])]],
	['www.n-tv.de/test, test', [paragraph([link('//www.n-tv.de/test', [plain('www.n-tv.de/test')]), plain(', test')])]],
	['www.n-tv.de/, test', [paragraph([link('//www.n-tv.de/', [plain('www.n-tv.de/')]), plain(', test')])]],
	['www.n-tv.de, test', [paragraph([link('//www.n-tv.de', [plain('www.n-tv.de')]), plain(', test')])]],
	['https://www.n-tv.de, test', [paragraph([link('https://www.n-tv.de', [plain('https://www.n-tv.de')]), plain(', test')])]],
	['http://te_st.com', [paragraph([link('http://te_st.com', [plain('http://te_st.com')])])]],
	['www.te_st.com', [paragraph([link('//www.te_st.com', [plain('www.te_st.com')])])]],
	['[google_search](http://google.com)', [paragraph([link('http://google.com', [plain('google_search')])])]],
	['app...https://chat.example.invalid https://chat.example.invalid', [paragraph([plain('app...https://chat.example.invalid '), link('https://chat.example.invalid')])]],
	[
		'Hey check it out the best communication platform https://chat.example.invalid! There is not discussion about it.',
		[
			paragraph([
				plain('Hey check it out the best communication platform '),
				link('https://chat.example.invalid'),
				plain('! There is not discussion about it.'),
			]),
		],
	],
	['This is a normal phrase.This in another phrase.', [paragraph([plain('This is a normal phrase.This in another phrase.')])]],
	[
		'https://assets.example.invalid/sample',
		[paragraph([link('https://assets.example.invalid/sample')])],
	],
	[
		'https://chat.example.invalid/(W(601))/Main?ScreenId=GI000027',
		[paragraph([link('https://chat.example.invalid/(W(601))/Main?ScreenId=GI000027')])],
	],
	[
		'https://examplechat.atlassian.net/browse/OC-718?filter=10078&jql=%22Defect%20from%5BVersion%20Picker%20(multiple%20versions)%5D%22%20%3D%206.0.0%20AND%20%22Defect%20from%5BVersion%20Picker%20(multiple%20versions)%5D%22%20%3D%206.0.0%20AND%20created%20%3E%3D%20-48h%20ORDER%20BY%20cf%5B10070%5D%20ASC%2C%20status%20ASC%2C%20created%20DESC',
		[
			paragraph([
				link(
					'https://examplechat.atlassian.net/browse/OC-718?filter=10078&jql=%22Defect%20from%5BVersion%20Picker%20(multiple%20versions)%5D%22%20%3D%206.0.0%20AND%20%22Defect%20from%5BVersion%20Picker%20(multiple%20versions)%5D%22%20%3D%206.0.0%20AND%20created%20%3E%3D%20-48h%20ORDER%20BY%20cf%5B10070%5D%20ASC%2C%20status%20ASC%2C%20created%20DESC',
				),
			]),
		],
	],
	['go to https://www.google.com.', [paragraph([plain('go to '), link('https://www.google.com'), plain('.')])]],
	['https://www.google.com.', [paragraph([link('https://www.google.com'), plain('.')])]],
	['https://www.google.com!', [paragraph([link('https://www.google.com'), plain('!')])]],
	['visit www.google.com.', [paragraph([plain('visit '), link('//www.google.com', [plain('www.google.com')]), plain('.')])]],
])('parses %p', (input, output) => {
	expect(parse(input)).toEqual(output);
});

describe('autoLink with custom hosts settings comming from ZEKI AI CHAT', () => {
	test.each([
		['http://gitlab.local', [paragraph([link('http://gitlab.local', [plain('http://gitlab.local')])])]],
		['gitlab.local', [paragraph([link('//gitlab.local', [plain('gitlab.local')])])]],
		['internaltool.intranet', [paragraph([link('//internaltool.intranet', [plain('internaltool.intranet')])])]],
	])('parses %p', (input, output) => {
		expect(parse(input, { customDomains: ['local', 'intranet'] })).toEqual(output);
	});
});

describe('autoLink WITHOUT custom hosts settings comming from ZEKI AI CHAT', () => {
	test.each([['https://internaltool.testt', [paragraph([plain('https://internaltool.testt')])]]])('parses %p', (input, output) => {
		expect(parse(input, { customDomains: ['local'] })).toEqual(output);
	});
});

describe('autoLink helper function', () => {
	it('should preserve the original protocol if the protocol is http or https', () => {
		expect(autoLink('https://chat.example.invalid/test')).toEqual(link('https://chat.example.invalid/test'));

		expect(autoLink('https://chat.example.invalid/test')).toEqual(link('https://chat.example.invalid/test'));
	});

	it('should preserve the original protocol for invalid absolute URLs', () => {
		expect(autoLink('https://chat.example.invalid')).toMatchObject(link('https://chat.example.invalid'));
		expect(autoLink('https://chat.example.invalid')).toMatchObject(link('https://chat.example.invalid'));
	});

	it('should preserve the original protocol even if for custom protocols', () => {
		expect(autoLink('custom://chat.example.invalid/test')).toEqual(link('custom://chat.example.invalid/test'));
	});

	it('should return // as the protocol if // is the protocol specified', () => {
		expect(autoLink('//chat.example.invalid/test')).toEqual(link('//chat.example.invalid/test'));
	});

	it("should return an url concatenated '//' if the url has no protocol", () => {
		expect(autoLink('chat.example.invalid/test')).toEqual(link('//chat.example.invalid/test', [plain('chat.example.invalid/test')]));
	});

	it("should return an url concatenated '//' if the url has no protocol and has sub-domain", () => {
		expect(autoLink('spark-public.s3.amazonaws.com')).toEqual(
			link('//spark-public.s3.amazonaws.com', [plain('spark-public.s3.amazonaws.com')]),
		);
	});

	it("should return an plain text url due to invalid TLD that's validate with the external library TLDTS", () => {
		expect(autoLink('examplechattt/url_path')).toEqual(plain('examplechattt/url_path'));
	});
});
