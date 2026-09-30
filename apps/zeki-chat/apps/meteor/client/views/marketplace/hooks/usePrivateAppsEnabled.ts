import { useSetting } from '@zeki.chat/ui-contexts';

export const usePrivateAppsEnabled = () => !useSetting('Zeki_Local_Only', true);
