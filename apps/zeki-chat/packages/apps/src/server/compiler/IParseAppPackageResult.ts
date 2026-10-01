import type { IAppInfo } from '@zeki.chat/apps-engine/definition/metadata';

import type { AppImplements } from './AppImplements';

export interface IParseAppPackageResult {
	info: IAppInfo;
	files: { [key: string]: string };
	languageContent: { [key: string]: object };
	implemented: AppImplements;
}
