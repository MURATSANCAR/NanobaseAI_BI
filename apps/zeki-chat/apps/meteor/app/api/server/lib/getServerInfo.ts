import type { IWorkspaceInfo } from '@zeki.chat/core-typings';

import { getTrimmedServerVersion } from './getTrimmedServerVersion';
import { hasPermissionAsync } from '../../../authorization/server/functions/hasPermission';
import { Info, minimumClientVersions } from '../../../utils/zekichat.info';

// Zeki: no supported-versions token and no cloud workspace id; nothing is fetched from ZEKI AI CHAT services.
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
