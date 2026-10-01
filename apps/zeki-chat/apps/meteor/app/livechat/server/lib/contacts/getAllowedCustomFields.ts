import type { ILivechatCustomField } from '@zeki.chat/core-typings';
import { LivechatCustomField } from '@zeki.chat/models';

export async function getAllowedCustomFields(): Promise<Pick<ILivechatCustomField, '_id' | 'label' | 'regexp' | 'required'>[]> {
	return LivechatCustomField.findByScope(
		'visitor',
		{
			projection: { _id: 1, label: 1, regexp: 1, required: 1 },
		},
		false,
	).toArray();
}
