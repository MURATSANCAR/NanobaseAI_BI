import type { IApiEndpointMetadata } from '@zeki.chat/apps-engine/definition/api';
import type { AppScreenshot } from '@zeki.chat/core-typings';

import type { ISettings } from '../../../apps/@types/IOrchestrator';
import type { App } from '../types';

export type AppInfo = App & {
	settings?: ISettings;
	apis: Array<IApiEndpointMetadata>;
	screenshots: Array<AppScreenshot>;
};
