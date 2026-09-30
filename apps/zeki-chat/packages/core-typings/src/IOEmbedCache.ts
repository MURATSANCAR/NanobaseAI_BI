import type { IZekiChatRecord } from './IZekiChatRecord';

export interface IOEmbedCache extends IZekiChatRecord {
	data: any;
	updatedAt: Date; // TODO: this field name differs from `_updatedAt` on `IZekiChatRecord`, should we unify this?
}
