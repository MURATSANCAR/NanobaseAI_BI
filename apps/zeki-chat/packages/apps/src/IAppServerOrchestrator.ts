import type { Logger } from '@zeki.chat/logger';
import type { IAppsPersistenceModel } from '@zeki.chat/model-typings';

import type { AppBridges, AppEvents, AppMetadataStorage } from './AppsEngine';
import type { IAppServerNotifier } from './IAppServerNotifier';
import type { IAppConvertersMap } from './converters';
import type { AppManager } from './server/AppManager';
import type { AppSourceStorage } from './server/storage';

export interface IAppServerOrchestrator {
	initialize(): void;
	isInitialized(): boolean;
	isLoaded(): boolean;
	getNotifier(): IAppServerNotifier;
	isDebugging(): boolean;
	debugLog(...args: any[]): void;
	getManager(): AppManager;
	getConverters(): IAppConvertersMap;
	getPersistenceModel(): IAppsPersistenceModel;
	getZekiChatLogger(): Logger;
	triggerEvent(event: AppEvents, ...payload: any[]): Promise<any>;
	getBridges(): AppBridges;
	getStorage(): AppMetadataStorage;
	getAppSourceStorage(): AppSourceStorage;
}
