import type { IOutboundMessageProviderService } from '@zeki.chat/core-typings';
import { makeFunction } from '@zeki.chat/patch-injection';

export const getOutboundService = makeFunction((): IOutboundMessageProviderService => {
	throw new Error('error-no-license');
});
