import { expect } from 'chai';
import { describe, it } from 'mocha';

import { extractUrlsFromMessageAST } from './extractUrlsFromMessageAST';

describe('extractUrlsFromMessageAST', () => {
	it('should extract URLs from LINK nodes', () => {
		const md = [
			{
				type: 'PARAGRAPH',
				value: [
					{
						type: 'LINK',
						value: {
							src: {
								type: 'PLAIN_TEXT',
								value: 'https://chat.example.invalid',
							},
							label: [
								{
									type: 'PLAIN_TEXT',
									value: 'chat.example.invalid',
								},
							],
						},
					},
				],
			},
		];

		const urls = extractUrlsFromMessageAST(md as any);
		expect(urls).to.deep.equal(['https://chat.example.invalid']);
	});

	it('should convert // prefix to https://', () => {
		const md = [
			{
				type: 'PARAGRAPH',
				value: [
					{
						type: 'LINK',
						value: {
							src: {
								type: 'PLAIN_TEXT',
								value: '//github.com/ZekiChat/ZEKI AI CHAT',
							},
							label: [
								{
									type: 'PLAIN_TEXT',
									value: 'github.com/ZekiChat/ZEKI AI CHAT',
								},
							],
						},
					},
				],
			},
		];

		const urls = extractUrlsFromMessageAST(md as any);
		expect(urls).to.deep.equal(['https://assets.example.invalid/sample']);
	});

	it('should handle multiple links', () => {
		const md = [
			{
				type: 'PARAGRAPH',
				value: [
					{
						type: 'LINK',
						value: {
							src: {
								type: 'PLAIN_TEXT',
								value: 'https://chat.example.invalid',
							},
							label: [
								{
									type: 'PLAIN_TEXT',
									value: 'chat.example.invalid',
								},
							],
						},
					},
					{
						type: 'PLAIN_TEXT',
						value: ' and ',
					},
					{
						type: 'LINK',
						value: {
							src: {
								type: 'PLAIN_TEXT',
								value: '//github.com/ZekiChat',
							},
							label: [
								{
									type: 'PLAIN_TEXT',
									value: 'github.com/ZekiChat',
								},
							],
						},
					},
				],
			},
		];

		const urls = extractUrlsFromMessageAST(md as any);
		expect(urls).to.deep.equal(['https://chat.example.invalid', 'https://github.com/examplechat']);
	});

	it('should return empty array for undefined or non-array input', () => {
		expect(extractUrlsFromMessageAST(undefined)).to.deep.equal([]);
		expect(extractUrlsFromMessageAST(null as any)).to.deep.equal([]);
		expect(extractUrlsFromMessageAST({} as any)).to.deep.equal([]);
	});
});
