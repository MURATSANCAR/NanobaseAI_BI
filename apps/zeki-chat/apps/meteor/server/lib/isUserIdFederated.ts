import { isUserFederated } from '@zeki.chat/core-typings';
import { Users } from '@zeki.chat/models';

export const isUserIdFederated = async (userId: string): Promise<boolean> => {
	const user = await Users.findOneById(userId, { projection: { federated: 1 } });

	if (!user) {
		return false;
	}
	return isUserFederated(user);
};
