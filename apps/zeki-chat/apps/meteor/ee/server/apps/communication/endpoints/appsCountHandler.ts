import type { AppManager } from '@zeki.chat/apps/dist/server/AppManager';

import { API } from '../../../../../app/api/server';
import { getInstallationSourceFromAppStorageItem } from '../../../../../lib/apps/getInstallationSourceFromAppStorageItem';
import type { AppsRestApi } from '../rest';

export const registerAppsCountHandler = ({ api, _manager }: AppsRestApi) =>
	void api.addRoute(
		'count',
		{ authRequired: false },
		{
			async get() {
				const manager = _manager as AppManager;

				const apps = await manager.get({ enabled: true });

				return API.v1.success({
					totalMarketplaceEnabled: apps.filter((app) => getInstallationSourceFromAppStorageItem(app.getStorageItem()) === 'marketplace')
						.length,
					totalPrivateEnabled: apps.filter((app) => getInstallationSourceFromAppStorageItem(app.getStorageItem()) === 'private').length,
				});
			},
		},
	);
