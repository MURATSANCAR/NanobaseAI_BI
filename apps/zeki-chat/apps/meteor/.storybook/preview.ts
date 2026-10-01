import type { Decorator, Parameters } from '@storybook/react';

import { zekiChatDecorator } from './decorators';

export const decorators: Decorator[] = [zekiChatDecorator];

export const parameters: Parameters = {
	backgrounds: {
		grid: {
			cellSize: 4,
			cellAmount: 4,
			opacity: 0.5,
		},
	},
	options: {
		storySort: {
			method: 'alphabetical',
			order: ['Components', '*', 'Enterprise'],
		},
	},
};
export const tags = ['autodocs'];
