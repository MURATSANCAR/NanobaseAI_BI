import type { IUpload } from '@zeki.chat/core-typings';

import type { IAppsUpload } from '../AppsEngine';

export interface IAppUploadsConverter {
	convertById(uploadId: string): Promise<IAppsUpload | undefined>;
	convertToApp(upload: undefined | null): Promise<undefined>;
	convertToApp(upload: IUpload): Promise<IAppsUpload>;
	convertToApp(upload: IUpload | undefined | null): Promise<IAppsUpload | undefined>;
	convertToZekiChat(upload: undefined | null): undefined;
	convertToZekiChat(upload: IAppsUpload): IUpload;
	convertToZekiChat(upload: IAppsUpload | undefined | null): IUpload | undefined;
}
