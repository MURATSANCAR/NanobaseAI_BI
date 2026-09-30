import type { IMessageRead } from '@zeki.chat/apps-engine/definition/accessors';
import type { IMessage } from '@zeki.chat/apps-engine/definition/messages';
import type { IRoom } from '@zeki.chat/apps-engine/definition/rooms';
import type { IUser } from '@zeki.chat/apps-engine/definition/users';

import type { MessageBridge } from '../bridges/MessageBridge';

export class MessageRead implements IMessageRead {
	constructor(
		private messageBridge: MessageBridge,
		private appId: string,
	) {}

	public getById(id: string): Promise<IMessage> {
		return this.messageBridge.doGetById(id, this.appId);
	}

	public async getSenderUser(messageId: string): Promise<IUser> {
		const msg = await this.messageBridge.doGetById(messageId, this.appId);

		if (!msg) {
			return undefined;
		}

		return msg.sender;
	}

	public async getRoom(messageId: string): Promise<IRoom> {
		const msg = await this.messageBridge.doGetById(messageId, this.appId);

		if (!msg) {
			return undefined;
		}

		return msg.room;
	}
}
