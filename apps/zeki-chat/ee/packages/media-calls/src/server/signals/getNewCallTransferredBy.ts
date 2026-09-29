import type { IMediaCall } from '@zeki.chat/core-typings';
import type { CallContact } from '@zeki.chat/media-signaling';

export function getNewCallTransferredBy(call: IMediaCall): CallContact | null {
	const { createdBy, parentCallId, caller, callee } = call;

	if (!createdBy || !parentCallId) {
		return null;
	}

	if (createdBy.type === caller.type && createdBy.id === caller.id) {
		return null;
	}

	if (createdBy.type === callee.type && createdBy.id === callee.id) {
		return null;
	}

	return createdBy;
}
