import type { IMessage } from '@zeki.chat/core-typings';
import { Rooms } from '@zeki.chat/models';

import { TranslationProviderRegistry } from '..';

export const translateMessage = async (targetLanguage?: string, message?: IMessage) => {
	if (!TranslationProviderRegistry.enabled) {
		return;
	}
	if (!message?.rid) {
		return;
	}

	const room = await Rooms.findOneById(message?.rid);
	let translatedMessage;

	if (message && room) {
		translatedMessage = await TranslationProviderRegistry.translateMessage(message, room, targetLanguage);
	}

	if (!translatedMessage) {
		return;
	}

	return translatedMessage;
};
