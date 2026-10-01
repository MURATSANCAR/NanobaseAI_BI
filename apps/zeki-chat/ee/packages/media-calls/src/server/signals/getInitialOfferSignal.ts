import type { IMediaCall } from '@zeki.chat/core-typings';
import type { CallRole, ServerMediaSignalRemoteSDP } from '@zeki.chat/media-signaling';
import { MediaCallNegotiations } from '@zeki.chat/models';

export async function getInitialOfferSignal(call: IMediaCall, role: CallRole): Promise<ServerMediaSignalRemoteSDP | null> {
	const { [role]: actor } = call;
	if (!actor.contractId) {
		return null;
	}

	const negotiation = await MediaCallNegotiations.findLatestByCallId(call._id);
	if (!negotiation?.offer || negotiation.offerer === role) {
		return null;
	}

	return {
		callId: call._id,
		toContractId: actor.contractId,
		type: 'remote-sdp',
		sdp: negotiation.offer,
		negotiationId: negotiation._id,
		streams: negotiation.offerStreams,
	};
}
