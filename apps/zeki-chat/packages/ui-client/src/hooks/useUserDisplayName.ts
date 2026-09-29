import type { IUser } from '@zeki.chat/core-typings';
import { getUserDisplayName } from '@zeki.chat/core-typings';
import { useSetting } from '@zeki.chat/ui-contexts';

export const useUserDisplayName = ({ name, username }: Pick<IUser, 'name' | 'username'>): string | undefined => {
	const useRealName = useSetting('UI_Use_Real_Name');

	return getUserDisplayName(name, username, !!useRealName);
};
