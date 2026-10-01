import type { ILogEntry } from '@zeki.chat/apps-engine/definition/accessors';
import type { AppMethod } from '@zeki.chat/apps-engine/definition/metadata';

export interface ILoggerStorageEntry {
	appId: string;
	method: `${AppMethod}`;
	entries: Array<ILogEntry>;
	startTime: Date;
	endTime: Date;
	totalTime: number;
	instanceId?: string;
	// Internal value to be used for sorting
	_createdAt: Date;
}
