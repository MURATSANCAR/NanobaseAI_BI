import type { ZekichatI18nKeys } from '@zeki.chat/i18n';

import type { Importer } from '../classes/Importer';

export type ImporterInfo = {
	key: string;
	name: ZekichatI18nKeys;
	visible: boolean; // Determines if this importer can be selected by the user in the New Import screen.
	importer: typeof Importer;
};
