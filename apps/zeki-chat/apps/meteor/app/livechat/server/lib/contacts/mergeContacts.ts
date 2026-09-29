import type { ILivechatContact, ILivechatContactVisitorAssociation } from '@zeki.chat/core-typings';
import { makeFunction } from '@zeki.chat/patch-injection';
import type { ClientSession } from 'mongodb';

export const mergeContacts = makeFunction(
	async (_contactId: string, _visitor: ILivechatContactVisitorAssociation, _session?: ClientSession): Promise<ILivechatContact | null> =>
		null,
);
