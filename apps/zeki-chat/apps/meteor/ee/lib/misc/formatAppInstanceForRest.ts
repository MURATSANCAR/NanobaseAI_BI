import type { ProxiedApp } from '@zeki.chat/apps/dist/server/ProxiedApp';
import type { AppLicenseValidationResult } from '@zeki.chat/apps/dist/server/marketplace/license/AppLicenseValidationResult';
import type { IAppStorageItem } from '@zeki.chat/apps/dist/server/storage/IAppStorageItem';
import type { AppStatus } from '@zeki.chat/apps-engine/definition/AppStatus';
import type { IAppInfo } from '@zeki.chat/apps-engine/definition/metadata';
import type { AppStatusReport } from '@zeki.chat/core-services';
import type { App } from '@zeki.chat/core-typings';

import { getInstallationSourceFromAppStorageItem } from '../../../lib/apps/getInstallationSourceFromAppStorageItem';

interface IAppInfoRest extends IAppInfo {
	status: AppStatus;
	languages: IAppStorageItem['languageContent'];
	licenseValidation?: AppLicenseValidationResult;
	private: boolean;
	migrated: boolean;
	clusterStatus?: App['clusterStatus'];
}

export async function formatAppInstanceForRest(app: ProxiedApp, clusterStatus?: AppStatusReport): Promise<IAppInfoRest> {
	const appRest: IAppInfoRest = {
		...app.getInfo(),
		status: await app.getStatus(),
		languages: app.getStorageItem().languageContent,
		private: getInstallationSourceFromAppStorageItem(app.getStorageItem()) === 'private',
		migrated: !!app.getStorageItem().migrated,
	};

	if (clusterStatus?.[app.getID()]) {
		appRest.clusterStatus = clusterStatus[app.getID()];
	}

	const licenseValidation = app.getLatestLicenseValidationResult();

	if (licenseValidation?.hasErrors || licenseValidation?.hasWarnings) {
		appRest.licenseValidation = licenseValidation;
	}

	return appRest;
}
