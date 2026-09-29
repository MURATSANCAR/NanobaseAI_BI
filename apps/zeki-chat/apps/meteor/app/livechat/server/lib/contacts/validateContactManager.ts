import type { IUser } from '@zeki.chat/core-typings';
import { Users } from '@zeki.chat/models';

export async function validateContactManager(contactManagerUserId: string) {
	const contactManagerUser = await Users.findOneAgentById<Pick<IUser, '_id'>>(contactManagerUserId, { projection: { _id: 1 } });
	if (!contactManagerUser) {
		throw new Error('error-contact-manager-not-found');
	}
}
