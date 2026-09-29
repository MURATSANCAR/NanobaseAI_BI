import type { IRoom, RoomType } from '@zeki.chat/core-typings';

import { ZekiChatError } from './ZekiChatError';

type OldUrlRoomErrorDetails =
	| { rid: IRoom['_id'] }
	| {
			type: RoomType;
			reference: string;
	  };

export class OldUrlRoomError extends ZekiChatError<'old-url-format', OldUrlRoomErrorDetails> {
	constructor(message = 'Old Url Format', details: OldUrlRoomErrorDetails) {
		super('old-url-format', message, details);
	}
}
