import type { IWorkspaceInfo } from '@rocket.chat/core-typings';

import { getTrimmedServerVersion } from './getTrimmedServerVersion';
import { hasPermissionAsync } from '../../../authorization/server/functions/hasPermission';
import { Info, minimumClientVersions } from '../../../utils/rocketchat.info';

// Zeki: no supported-versions token and no cloud workspace id; nothing is fetched from Rocket.Chat services.
export async function getServerInfo(userId?: string): Promise<IWorkspaceInfo> {
	const hasPermissionToViewStatistics = userId && (await hasPermissionAsync(userId, 'view-statistics'));

	return {
		version: getTrimmedServerVersion(),
		...(hasPermissionToViewStatistics && {
			info: {
				...Info,
			},
			version: Info.version,
		}),

		minimumClientVersions,
	};
}
