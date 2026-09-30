import { parameters, decorators } from '@zeki.chat/storybook-config/preview';
import type { Preview } from '@storybook/react';

const preview: Preview = {
	parameters: {
		...parameters,
	},
	decorators: [...decorators],
};

export default preview;
