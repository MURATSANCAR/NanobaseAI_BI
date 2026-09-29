import type { ISetting } from '@rocket.chat/core-typings';
import { useCapabilities } from '@rocket.chat/ui-client';

export const useHasSettingModule = (setting?: ISetting) => {
	const { data } = useCapabilities();
	if (!setting) throw new Error('No setting provided');
	return !setting.modules?.length || setting.modules.every((module) => data?.modules.includes(module));
};
