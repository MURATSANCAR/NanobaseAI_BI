import type { ILivechatBusinessHour } from '@zeki.chat/core-typings';
import { LivechatBusinessHourTypes } from '@zeki.chat/core-typings';
import moment from 'moment-timezone';

import type { IBusinessHourType } from './AbstractBusinessHour';
import { AbstractBusinessHourType } from './AbstractBusinessHour';

interface IExtraProperties {
	timezoneName?: string;
}

export class DefaultBusinessHour extends AbstractBusinessHourType implements IBusinessHourType {
	name = LivechatBusinessHourTypes.DEFAULT;

	getBusinessHour(): Promise<ILivechatBusinessHour | null> {
		return this.BusinessHourRepository.findOneDefaultBusinessHour();
	}

	async saveBusinessHour(businessHour: ILivechatBusinessHour & IExtraProperties): Promise<ILivechatBusinessHour> {
		const { timezoneName, ...businessHourData } = businessHour;

		if (!businessHourData._id) {
			return businessHourData;
		}
		businessHourData.timezone = {
			name: timezoneName || moment.tz.guess(),
			utc: this.getUTCFromTimezone(timezoneName),
		};
		await this.baseSaveBusinessHour(businessHourData);
		return businessHourData;
	}

	removeBusinessHourById(): Promise<void> {
		return Promise.resolve();
	}
}
