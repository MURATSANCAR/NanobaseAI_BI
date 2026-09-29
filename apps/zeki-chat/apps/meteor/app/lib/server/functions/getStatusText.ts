import { Users } from '@zeki.chat/models';

export const getStatusText = async function (userId: string): Promise<string | undefined> {
	if (!userId) {
		return;
	}

	const projection = {
		statusText: 1,
	};

	const options = {
		projection,
		limit: 1,
	};

	const data = await Users.findOneById(userId, options);
	return data?.statusText;
};
