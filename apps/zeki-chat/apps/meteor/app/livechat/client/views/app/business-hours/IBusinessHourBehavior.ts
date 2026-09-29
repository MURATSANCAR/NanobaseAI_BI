import type { ILivechatBusinessHour } from '@zeki.chat/core-typings';

export interface IBusinessHourBehavior {
	getView(): string;
	showCustomTemplate(businessHourData: ILivechatBusinessHour): boolean;
	showBackButton(): boolean;
}
