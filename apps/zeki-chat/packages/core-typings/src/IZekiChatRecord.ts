import type { WithId } from 'mongodb';
import * as z from 'zod';

import { TimestampSchema } from './utils';

export const IZekiChatRecordSchema = z.object({
	_id: z.string(),
	_updatedAt: TimestampSchema,
});

export interface IZekiChatRecord extends z.infer<typeof IZekiChatRecordSchema> {}

export type ZekiChatRecordDeleted<T> = WithId<T> & {
	_updatedAt: Date;
	_deletedAt: Date;
	__collection__: string;
};
