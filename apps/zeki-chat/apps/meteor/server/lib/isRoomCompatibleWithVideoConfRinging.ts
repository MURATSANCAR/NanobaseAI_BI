import type { IRoom } from '@zeki.chat/core-typings';

export const isRoomCompatibleWithVideoConfRinging = (roomType: IRoom['t'], roomUids: IRoom['uids']): boolean =>
	Boolean(roomType === 'd' && roomUids && roomUids.length <= 2);
