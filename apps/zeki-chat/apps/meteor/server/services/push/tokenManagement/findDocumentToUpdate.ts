import type { IPushToken } from '@zeki.chat/core-typings';
import { PushToken } from '@zeki.chat/models';

export async function findDocumentToUpdate(data: Partial<IPushToken>): Promise<IPushToken | null> {
	if (data._id) {
		const existingDoc = await PushToken.findOneById(data._id);
		if (existingDoc) {
			return existingDoc;
		}
	}

	// VoIP tokens MUST match the id
	if (data.voipToken) {
		return null;
	}

	if (data.token && data.appName) {
		return PushToken.findOneByTokenAndAppName(data.token, data.appName);
	}

	return null;
}
