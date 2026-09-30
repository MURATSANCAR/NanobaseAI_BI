import type { IZekiChatRecord } from './IZekiChatRecord';
import type { IUser } from './IUser';
import type { UserStatus } from './UserStatus';

export interface ICalendarEvent extends IZekiChatRecord {
	startTime: Date;
	endTime?: Date;

	uid: IUser['_id'];
	subject: string;
	description: string;
	notificationSent: boolean;

	externalId?: string | null;
	meetingUrl?: string | null;

	reminderMinutesBeforeStart?: number;
	reminderTime?: Date;

	busy?: boolean;
	previousStatus?: UserStatus;
}
