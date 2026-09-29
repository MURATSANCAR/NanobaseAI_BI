import type { IRoom, RoomType } from '@zeki.chat/core-typings';

import { ZekiChatError } from './ZekiChatError';

type RoomNotFoundErrorDetails =
	| { rid: IRoom['_id'] }
	| {
			type: RoomType;
			reference: string;
	  };

export class RoomNotFoundError extends ZekiChatError<'room-not-found', RoomNotFoundErrorDetails> {
	constructor(message = 'Room not found', details: RoomNotFoundErrorDetails) {
		super('room-not-found', message, details);
	}
}
