import type { IMessageExtender } from '@zeki.chat/apps-engine/definition/accessors';
import type { IMessage, IMessageAttachment } from '@zeki.chat/apps-engine/definition/messages';
import { ZekiChatAssociationModel } from '@zeki.chat/apps-engine/definition/metadata';

import { Utilities } from '../misc/Utilities';

export class MessageExtender implements IMessageExtender {
	public readonly kind: ZekiChatAssociationModel.MESSAGE;

	constructor(private msg: IMessage) {
		this.kind = ZekiChatAssociationModel.MESSAGE;

		if (!Array.isArray(msg.attachments)) {
			this.msg.attachments = [];
		}
	}

	public addCustomField(key: string, value: any): IMessageExtender {
		if (!this.msg.customFields) {
			this.msg.customFields = {};
		}

		if (this.msg.customFields[key]) {
			throw new Error(`The message already contains a custom field by the key: ${key}`);
		}

		if (key.includes('.')) {
			throw new Error(`The given key contains a period, which is not allowed. Key: ${key}`);
		}

		this.msg.customFields[key] = value;

		return this;
	}

	public addAttachment(attachment: IMessageAttachment): IMessageExtender {
		this.msg.attachments.push(attachment);

		return this;
	}

	public addAttachments(attachments: Array<IMessageAttachment>): IMessageExtender {
		this.msg.attachments = this.msg.attachments.concat(attachments);

		return this;
	}

	public getMessage(): IMessage {
		return Utilities.deepClone(this.msg);
	}
}
