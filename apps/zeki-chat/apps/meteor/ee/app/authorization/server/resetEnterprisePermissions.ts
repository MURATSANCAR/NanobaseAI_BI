import { Permissions } from '@zeki.chat/models';

import { guestPermissions } from '../lib/guestPermissions';

export const resetEnterprisePermissions = async function (): Promise<void> {
	await Permissions.updateMany(
		{
			_id: { $nin: guestPermissions },
			roles: 'guest',
		},
		{ $pull: { roles: 'guest' } },
	);
};
