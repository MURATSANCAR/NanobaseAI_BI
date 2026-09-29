import type { ILivechatContact, ILivechatContactVisitorAssociation } from '@zeki.chat/core-typings';
import { LivechatContacts } from '@zeki.chat/models';

export async function getContactIdByVisitor(visitor: ILivechatContactVisitorAssociation): Promise<ILivechatContact['_id'] | undefined> {
	const contact = await LivechatContacts.findOneByVisitor<Pick<ILivechatContact, '_id'>>(visitor, { projection: { _id: 1 } });

	return contact?._id;
}
