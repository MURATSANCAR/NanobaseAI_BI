import type { IRoom } from '@zeki.chat/core-typings';

import { ZekiChatError } from './ZekiChatError';

type NotSubscribedToRoomErrorDetails = { rid: IRoom['_id'] };

export class NotSubscribedToRoomError extends ZekiChatError<'not-subscribed-room', NotSubscribedToRoomErrorDetails> {
	public declare readonly reason: string;

	public declare readonly details: NotSubscribedToRoomErrorDetails;

	constructor(message = 'Not subscribed to this room', details: NotSubscribedToRoomErrorDetails) {
		super('not-subscribed-room', message, details);
	}
}
