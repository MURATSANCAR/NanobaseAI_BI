import type { RoomType, IRoom } from '@zeki.chat/core-typings';
import type { RoomToolboxActionConfig } from '@zeki.chat/ui-contexts';

const groupsDict = {
	l: 'live',
	d: 'direct',
	p: 'group',
	c: 'channel',
} as const satisfies Record<RoomType, RoomToolboxActionConfig['groups'][number]>;

export const getRoomGroup = (room: IRoom) => {
	if (room.teamMain) {
		return 'team';
	}

	if (room.t === 'd' && (room.uids?.length ?? 0) > 2) {
		return 'direct_multiple';
	}

	return groupsDict[room.t];
};
