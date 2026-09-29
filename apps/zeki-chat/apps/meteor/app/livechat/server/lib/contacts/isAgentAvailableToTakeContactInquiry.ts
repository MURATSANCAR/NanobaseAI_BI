import type { ILivechatContact, ILivechatVisitor, IOmnichannelSource } from '@zeki.chat/core-typings';
import { makeFunction } from '@zeki.chat/patch-injection';

export const isAgentAvailableToTakeContactInquiry = makeFunction(
	async (
		_visitorId: ILivechatVisitor['_id'],
		_source: IOmnichannelSource,
		_contactId: ILivechatContact['_id'],
	): Promise<{ error: string; value: false } | { value: true }> => ({
		value: true,
	}),
);
