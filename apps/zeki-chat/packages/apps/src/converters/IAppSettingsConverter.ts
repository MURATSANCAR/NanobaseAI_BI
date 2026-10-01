import type { ISetting } from '@zeki.chat/core-typings';

import type { IAppsSetting } from '../AppsEngine';

export interface IAppSettingsConverter {
	convertById(settingId: ISetting['_id']): Promise<IAppsSetting>;
	convertToApp(setting: ISetting): IAppsSetting;
}
