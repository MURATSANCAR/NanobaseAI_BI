import type { ServerMethods } from '@zeki.chat/ddp-client';
import { Meteor } from 'meteor/meteor';

import { insertOrUpdateEmoji } from '../lib/insertOrUpdateEmoji';

declare module '@zeki.chat/ddp-client' {
	// eslint-disable-next-line @typescript-eslint/naming-convention
	interface ServerMethods {
		insertOrUpdateEmoji(emojiData: {
			_id?: string;
			name: string;
			aliases: string;
			extension: string;
			previousName?: string;
			previousExtension?: string;
			newFile?: boolean;
		}): string | boolean;
	}
}

Meteor.methods<ServerMethods>({
	async insertOrUpdateEmoji(emojiData) {
		const emoji = await insertOrUpdateEmoji(this.userId, emojiData);

		if (!emojiData._id) {
			return emoji._id;
		}

		return !!emoji;
	},
});
