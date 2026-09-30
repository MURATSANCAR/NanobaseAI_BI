import type { ISetting } from '@zeki.chat/core-typings';

import type { IServiceClass } from './ServiceClass';

export interface IEnterpriseSettings extends IServiceClass {
	changeSettingValue(record: ISetting): undefined | ISetting['value'];
}
