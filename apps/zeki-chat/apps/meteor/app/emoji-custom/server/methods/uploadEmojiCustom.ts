import type { ServerMethods } from '@zeki.chat/ddp-client';
import { Meteor } from 'meteor/meteor';

import { uploadEmojiCustom } from '../lib/uploadEmojiCustom';

declare module '@zeki.chat/ddp-client' {
	// eslint-disable-next-line @typescript-eslint/naming-convention
	interface ServerMethods {
		uploadEmojiCustom(
			binaryContent: string,
			contentType: string,
			emojiData: {
				name: string;
				aliases?: string;
				extension: string;
			},
		): void;
	}
}

Meteor.methods<ServerMethods>({
	async uploadEmojiCustom(binaryContent, contentType, emojiData) {
		await uploadEmojiCustom(this.userId, binaryContent, contentType, emojiData);
	},
});
