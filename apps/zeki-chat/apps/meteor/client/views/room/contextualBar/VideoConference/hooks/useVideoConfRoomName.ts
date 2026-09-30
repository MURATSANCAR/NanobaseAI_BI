import type { IRoom } from '@zeki.chat/core-typings';
import { isDirectMessageRoom } from '@zeki.chat/core-typings';
import { useUserDisplayName } from '@zeki.chat/ui-client';
import { useUserSubscription } from '@zeki.chat/ui-contexts';

export const useVideoConfRoomName = (room: IRoom): string | undefined => {
	const subscription = useUserSubscription(room._id);
	const username = useUserDisplayName({ name: subscription?.fname, username: subscription?.name });

	return isDirectMessageRoom(room) ? username : room.fname || room.name;
};
