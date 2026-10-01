import type { ZekiChatRecordDeleted, IAuditLog } from '@zeki.chat/core-typings';
import { BaseRaw } from '@zeki.chat/models';
import type { Collection, Db } from 'mongodb';

export class AuditLogRaw extends BaseRaw<IAuditLog> {
	constructor(db: Db, trash?: Collection<ZekiChatRecordDeleted<IAuditLog>>) {
		super(db, 'audit_log', trash);
	}
}
