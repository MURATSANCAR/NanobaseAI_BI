import { Users } from '@zeki.chat/models';

export const checkEmailAvailability = async function (email: string): Promise<boolean> {
	return !(await Users.findOneByEmailAddress(email));
};
