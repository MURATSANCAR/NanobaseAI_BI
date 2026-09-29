import type { ILivechatContact } from '@zeki.chat/core-typings';
import { LivechatContacts } from '@zeki.chat/models';

export const patchContact = async (
	contactId: ILivechatContact['_id'],
	data: { set?: Partial<ILivechatContact>; unset?: Partial<Record<keyof ILivechatContact, '' | 1>> },
): Promise<ILivechatContact | null> => {
	const { set = {}, unset = {} } = data;

	if (Object.keys(set).length === 0 && Object.keys(unset).length === 0) {
		return LivechatContacts.findOneEnabledById(contactId);
	}
	return LivechatContacts.patchContact(contactId, data);
};
