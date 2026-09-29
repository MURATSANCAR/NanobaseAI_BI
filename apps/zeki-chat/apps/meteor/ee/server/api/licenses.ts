import { Capabilities } from '@zeki.chat/capabilities';
import { Users } from '@rocket.chat/models';
import { isLicensesInfoProps } from '@rocket.chat/rest-typings';

import { API } from '../../../app/api/server/api';
import { hasPermissionAsync } from '../../../app/authorization/server/functions/hasPermission';

// Zeki: read-only, local license info. The license upload endpoint and cloud announcement payload are removed.
API.v1.addRoute(
	'licenses.info',
	{ authRequired: true, validateParams: isLicensesInfoProps },
	{
		async get() {
			const unrestrictedAccess = await hasPermissionAsync(this.userId, 'view-privileged-setting');
			const loadCurrentValues = unrestrictedAccess && Boolean(this.queryParams.loadValues);

			const license = await Capabilities.getInfo({
				limits: unrestrictedAccess,
				license: unrestrictedAccess,
				currentValues: loadCurrentValues,
			});

			return API.v1.success({
				license,
			});
		},
	},
);

API.v1.addRoute(
	'licenses.maxActiveUsers',
	{ authRequired: true },
	{
		async get() {
			const maxActiveUsers = Capabilities.getMaxActiveUsers();
			const activeUsers = await Users.getActiveLocalUserCount();

			return API.v1.success({ maxActiveUsers: maxActiveUsers > 0 ? maxActiveUsers : null, activeUsers });
		},
	},
);
