'use strict';

Object.defineProperty(exports, '__esModule', { value: true });

const { createElement } = require('react');

// Zeki: violet badge with a white "Z" followed by the "ZEKI AI CHAT" wordmark.
const Mark = ({ color = 'currentColor', height = 32 }) =>
	createElement(
		'svg',
		{ role: 'img', 'aria-label': 'ZEKI AI CHAT', height, viewBox: '0 0 210 32', style: { maxWidth: '100%' }, xmlns: 'http://www.w3.org/2000/svg' },
		createElement('rect', { x: 0, y: 0, width: 32, height: 32, rx: 8, fill: '#7C5CFF' }),
		createElement('path', { d: 'M10 10h12v2.6L13.6 21H22v3H10v-2.6L18.4 13H10z', fill: '#fff' }),
		createElement(
			'text',
			{ x: 42, y: 23, fill: color, fontFamily: "'Plus Jakarta Sans','DM Sans',system-ui,sans-serif", fontSize: 19, fontWeight: 700 },
			'ZEKI AI CHAT',
		),
	);

const RocketChatLogo = ({ color } = {}) => createElement(Mark, { color });

const TaggedRocketChatLogo = ({ tagTitle, tagBackground, color, ...props } = {}) =>
	createElement(
		'div',
		{ ...props, style: { display: 'inline-flex', alignItems: 'center', gap: 8, ...(props.style || {}) } },
		createElement(Mark, { color }),
		tagTitle
			? createElement(
					'span',
					{
						style: {
							background: tagBackground || '#7C5CFF',
							color: '#fff',
							borderRadius: 4,
							padding: '2px 6px',
							fontSize: 11,
							fontWeight: 700,
							textTransform: 'uppercase',
						},
					},
					tagTitle,
				)
			: null,
	);

exports.RocketChatLogo = RocketChatLogo;
exports.TaggedRocketChatLogo = TaggedRocketChatLogo;
