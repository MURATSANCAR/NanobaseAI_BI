import type { IUser } from '@zeki.chat/core-typings';
import { cronJobs } from '@zeki.chat/cron';
import { CalendarEvent } from '@zeki.chat/models';

import { generateCronJobId } from './generateCronJobId';
import { settings } from '../../../../app/settings/server';

export async function cancelUpcomingStatusChanges(uid: IUser['_id'], endTime = new Date()): Promise<void> {
	const hasBusyStatusSetting = settings.get<boolean>('Calendar_BusyStatus_Enabled');
	if (!hasBusyStatusSetting) {
		return;
	}

	const events = await CalendarEvent.findEligibleEventsForCancelation(uid, endTime).toArray();

	for await (const event of events) {
		const statusChangeJobId = generateCronJobId(event._id, event.uid, 'status');
		if (await cronJobs.has(statusChangeJobId)) {
			await cronJobs.remove(statusChangeJobId);
		}
	}
}
