import type { IDiscussionBuilder as _IDiscussionBuilder } from '@zeki.chat/apps-engine/definition/accessors/IDiscussionBuilder';
import type { IMessage } from '@zeki.chat/apps-engine/definition/messages/IMessage';
import type { IRoom } from '@zeki.chat/apps-engine/definition/rooms/IRoom';
import type { IRoomBuilder } from '@zeki.chat/apps-engine/definition/accessors/IRoomBuilder';

import type { ZekiChatAssociationModel as _ZekiChatAssociationModel } from '@zeki.chat/apps-engine/definition/metadata/ZekiChatAssociations';
import type { RoomType as _RoomType } from '@zeki.chat/apps-engine/definition/rooms/RoomType';

import { RoomBuilder } from './RoomBuilder.ts';
import { require } from '../../../lib/require.ts';

const { ZekiChatAssociationModel } = require('@zeki.chat/apps-engine/definition/metadata/ZekiChatAssociations.js') as {
	ZekiChatAssociationModel: typeof _ZekiChatAssociationModel;
};

const { RoomType } = require('@zeki.chat/apps-engine/definition/rooms/RoomType.js') as { RoomType: typeof _RoomType };

export interface IDiscussionBuilder extends _IDiscussionBuilder, IRoomBuilder {}

export class DiscussionBuilder extends RoomBuilder implements IDiscussionBuilder {
	public kind: _ZekiChatAssociationModel.DISCUSSION;

	private reply?: string;

	private parentMessage?: IMessage;

	constructor(data?: Partial<IRoom>) {
		super(data);
		this.kind = ZekiChatAssociationModel.DISCUSSION;
		this.room.type = RoomType.PRIVATE_GROUP;
	}

	public setParentRoom(parentRoom: IRoom): IDiscussionBuilder {
		this.room.parentRoom = parentRoom;
		return this;
	}

	public getParentRoom(): IRoom {
		return this.room.parentRoom!;
	}

	public setReply(reply: string): IDiscussionBuilder {
		this.reply = reply;
		return this;
	}

	public getReply(): string {
		return this.reply!;
	}

	public setParentMessage(parentMessage: IMessage): IDiscussionBuilder {
		this.parentMessage = parentMessage;
		return this;
	}

	public getParentMessage(): IMessage {
		return this.parentMessage!;
	}
}
