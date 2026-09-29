import type { ISMSProviderConstructor } from '@zeki.chat/core-typings';

import { Twilio } from './twilio';

export const registerSmsProviders = (register: (n: string, s: ISMSProviderConstructor) => void): void => {
	register('twilio', Twilio);
};
