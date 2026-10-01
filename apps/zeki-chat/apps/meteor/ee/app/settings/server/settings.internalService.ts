import { ServiceClassInternal } from '@zeki.chat/core-services';
import type { IEnterpriseSettings } from '@zeki.chat/core-services';
import type { ISetting } from '@zeki.chat/core-typings';

import { changeSettingValue } from './settings';

export class EnterpriseSettings extends ServiceClassInternal implements IEnterpriseSettings {
	protected name = 'ee-settings';

	protected override internal = true;

	changeSettingValue(record: ISetting): undefined | ISetting['value'] {
		return changeSettingValue(record);
	}
}
