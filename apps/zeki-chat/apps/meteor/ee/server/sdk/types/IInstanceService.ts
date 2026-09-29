import type { AppStatusReport } from '@zeki.chat/core-services';
import type { BrokerNode } from 'moleculer';

export interface IInstanceService {
	getInstances(): Promise<BrokerNode[]>;
	getAppsStatusInInstances(): Promise<AppStatusReport>;
}
