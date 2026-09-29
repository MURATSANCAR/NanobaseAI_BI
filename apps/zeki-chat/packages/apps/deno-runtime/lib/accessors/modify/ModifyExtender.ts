import type { IModifyExtender } from '@zeki.chat/apps-engine/definition/accessors/IModifyExtender';
import type { IMessage } from '@zeki.chat/apps-engine/definition/messages/IMessage';
import type { IMessageExtender } from '@zeki.chat/apps-engine/definition/accessors/IMessageExtender';
import type { IRoomExtender } from '@zeki.chat/apps-engine/definition/accessors/IRoomExtender';
import type { IVideoConferenceExtender } from '@zeki.chat/apps-engine/definition/accessors/IVideoConferenceExtend';
import type { IUser } from '@zeki.chat/apps-engine/definition/users/IUser';
import type { VideoConference } from '@zeki.chat/apps-engine/definition/videoConferences/IVideoConference';
import type { IRoom } from '@zeki.chat/apps-engine/definition/rooms/IRoom';
import type { ZekiChatAssociationModel as _ZekiChatAssociationModel } from '@zeki.chat/apps-engine/definition/metadata/ZekiChatAssociations';

import * as Messenger from '../../messenger.ts';
import { AppObjectRegistry } from '../../../AppObjectRegistry.ts';
import { MessageExtender } from '../extenders/MessageExtender.ts';
import { RoomExtender } from '../extenders/RoomExtender.ts';
import { VideoConferenceExtender } from '../extenders/VideoConferenceExtend.ts';
import { require } from '../../../lib/require.ts';
import { formatErrorResponse } from '../formatResponseErrorHandler.ts';

const { ZekiChatAssociationModel } = require('@zeki.chat/apps-engine/definition/metadata/ZekiChatAssociations.js') as {
	ZekiChatAssociationModel: typeof _ZekiChatAssociationModel;
};

export class ModifyExtender implements IModifyExtender {
	constructor(private readonly senderFn: typeof Messenger.sendRequest) {}

	public async extendMessage(messageId: string, updater: IUser): Promise<IMessageExtender> {
		const result = await this.senderFn({
			method: 'bridges:getMessageBridge:doGetById',
			params: [messageId, AppObjectRegistry.get('id')],
		}).catch((err) => {
			throw formatErrorResponse(err);
		});

		const msg = result.result as IMessage;

		msg.editor = updater;
		msg.editedAt = new Date();

		return new MessageExtender(msg);
	}

	public async extendRoom(roomId: string, _updater: IUser): Promise<IRoomExtender> {
		const result = await this.senderFn({
			method: 'bridges:getRoomBridge:doGetById',
			params: [roomId, AppObjectRegistry.get('id')],
		}).catch((err) => {
			throw formatErrorResponse(err);
		});

		const room = result.result as IRoom;

		room.updatedAt = new Date();

		return new RoomExtender(room);
	}

	public async extendVideoConference(id: string): Promise<IVideoConferenceExtender> {
		const result = await this.senderFn({
			method: 'bridges:getVideoConferenceBridge:doGetById',
			params: [id, AppObjectRegistry.get('id')],
		}).catch((err) => {
			throw formatErrorResponse(err);
		});

		const call = result.result as VideoConference;

		call._updatedAt = new Date();

		return new VideoConferenceExtender(call);
	}

	public async finish(extender: IMessageExtender | IRoomExtender | IVideoConferenceExtender): Promise<void> {
		switch (extender.kind) {
			case ZekiChatAssociationModel.MESSAGE:
				await this.senderFn({
					method: 'bridges:getMessageBridge:doUpdate',
					params: [(extender as IMessageExtender).getMessage(), AppObjectRegistry.get('id')],
				}).catch((err) => {
					throw formatErrorResponse(err);
				});
				break;
			case ZekiChatAssociationModel.ROOM:
				await this.senderFn({
					method: 'bridges:getRoomBridge:doUpdate',
					params: [
						(extender as IRoomExtender).getRoom(),
						(extender as IRoomExtender).getUsernamesOfMembersBeingAdded(),
						AppObjectRegistry.get('id'),
					],
				}).catch((err) => {
					throw formatErrorResponse(err);
				});
				break;
			case ZekiChatAssociationModel.VIDEO_CONFERENCE:
				await this.senderFn({
					method: 'bridges:getVideoConferenceBridge:doUpdate',
					params: [(extender as IVideoConferenceExtender).getVideoConference(), AppObjectRegistry.get('id')],
				}).catch((err) => {
					throw formatErrorResponse(err);
				});
				break;
			default:
				throw new Error('Invalid extender passed to the ModifyExtender.finish function.');
		}
	}
}
