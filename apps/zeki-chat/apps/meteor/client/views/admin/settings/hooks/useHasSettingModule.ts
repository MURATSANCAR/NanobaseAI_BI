import type { ISetting } from '@zeki.chat/core-typings';
import { useCapabilities } from '@zeki.chat/ui-client';

export const useHasSettingModule = (setting?: ISetting) => {
	const { data } = useCapabilities();
	if (!setting) throw new Error('No setting provided');
	return !setting.modules?.length || setting.modules.every((module) => data?.modules.includes(module));
};
