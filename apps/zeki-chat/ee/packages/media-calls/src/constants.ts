import type { CallFeature } from '@zeki.chat/media-signaling';

export const DEFAULT_CALL_FEATURES: CallFeature[] = ['audio'];
export const SIP_CALL_FEATURES: CallFeature[] = ['audio', 'transfer', 'hold'];
