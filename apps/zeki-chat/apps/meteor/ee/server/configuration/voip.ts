import { MediaCall } from '@rocket.chat/core-services';
import { Capabilities } from '@zeki.chat/capabilities';

import { addSettings } from '../settings/voip';

Capabilities.onReady(async () => {
	await addSettings();

	await MediaCall.hangupExpiredCalls();
});
