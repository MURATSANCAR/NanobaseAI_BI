import type { ILivechatBusinessHour } from '@zeki.chat/core-typings';
import { LivechatBusinessHourTypes } from '@zeki.chat/core-typings';

import type { IBusinessHourBehavior } from '../../../../livechat/client/views/app/business-hours/IBusinessHourBehavior';

export class MultipleBusinessHoursBehavior implements IBusinessHourBehavior {
	getView(): string {
		return 'livechatBusinessHours';
	}

	showCustomTemplate(businessHourData: ILivechatBusinessHour): boolean {
		return !businessHourData._id || businessHourData.type !== LivechatBusinessHourTypes.DEFAULT;
	}

	showBackButton(): boolean {
		return true;
	}
}
