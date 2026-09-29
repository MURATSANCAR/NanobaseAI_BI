import type { IMediaCall } from '@zeki.chat/core-typings';
import type { VoipPushNotificationType } from '@zeki.chat/media-calls';

export function getPushNotificationType(call: IMediaCall): VoipPushNotificationType {
	if (call.acceptedAt) {
		return 'answeredElsewhere';
	}

	if (call.endedBy?.id === call.callee.id || call.hangupReason === 'rejected') {
		return 'declinedElsewhere';
	}

	if (call.endedBy?.id === call.caller.id) {
		return 'remoteEnded';
	}

	if (call.ended) {
		return 'unanswered';
	}

	return 'incoming_call';
}
