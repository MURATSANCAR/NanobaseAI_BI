import type { IOmnichannelSystemMessage } from '@zeki.chat/core-typings';
import { Messages } from '@zeki.chat/models';
import type { PaginatedResult } from '@zeki.chat/rest-typings';

const normalizeTransferHistory = ({ transferData }: IOmnichannelSystemMessage): IOmnichannelSystemMessage['transferData'] => transferData;

const removeNulls = <S>(value: S | undefined): value is S => value != null;

export async function findLivechatTransferHistory({
	rid,
	pagination: { offset, count, sort },
}: {
	rid: string;
	pagination: { offset: number; count: number; sort: Record<string, number> };
}): Promise<PaginatedResult<{ history: IOmnichannelSystemMessage['transferData'][] }>> {
	const { cursor, totalCount } = Messages.findPaginated(
		{ rid, t: 'livechat_transfer_history' },
		{
			projection: { transferData: 1 },
			sort: sort || { ts: 1 },
			skip: offset,
			limit: count,
		},
	);

	const [history, total] = await Promise.all([cursor.map(normalizeTransferHistory).toArray(), totalCount]);

	return {
		history: history.filter(removeNulls),
		count: history.length,
		offset,
		total,
	};
}
