import { useSetting, usePermission } from '@zeki.chat/ui-contexts';
import type { RoomToolboxActionConfig } from '@zeki.chat/ui-contexts';
import { lazy, useMemo } from 'react';

const AutoTranslate = lazy(() => import('../../views/room/contextualBar/AutoTranslate'));

export const useAutotranslateRoomAction = () => {
	const permitted = usePermission('auto-translate');
	const enabled = useSetting('AutoTranslate_Enabled', false);

	return useMemo((): RoomToolboxActionConfig | undefined => {
		if (!permitted || !enabled) {
			return undefined;
		}

		return {
			id: 'autotranslate',
			groups: ['channel', 'group', 'direct', 'direct_multiple', 'team'],
			title: 'Auto_Translate',
			icon: 'language',
			tabComponent: AutoTranslate,
			order: 20,
			full: true,
			type: 'customization',
		};
	}, [enabled, permitted]);
};
