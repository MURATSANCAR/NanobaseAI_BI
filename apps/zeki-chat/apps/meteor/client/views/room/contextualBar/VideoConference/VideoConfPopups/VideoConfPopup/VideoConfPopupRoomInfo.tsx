import type { IRoom } from '@zeki.chat/core-typings';
import { isDirectMessageRoom, isMultipleDirectMessageRoom } from '@zeki.chat/core-typings';
import { RoomAvatar } from '@zeki.chat/ui-avatar';
import { useUser } from '@zeki.chat/ui-contexts';
import { VideoConfPopupInfo } from '@zeki.chat/ui-video-conf';
import type { ReactElement } from 'react';

import { RoomIcon } from '../../../../../../components/RoomIcon';
import ReactiveUserStatus from '../../../../../../components/UserStatus/ReactiveUserStatus';
import { useVideoConfRoomName } from '../../hooks/useVideoConfRoomName';

const VideoConfPopupRoomInfo = ({ room }: { room: IRoom }): ReactElement => {
	const ownUser = useUser();
	const [userId] = room?.uids?.filter((uid) => uid !== ownUser?._id) || [];
	const roomName = useVideoConfRoomName(room);
	const avatar = <RoomAvatar room={room} size='x40' />;

	if (isDirectMessageRoom(room)) {
		return (
			<VideoConfPopupInfo
				avatar={avatar}
				{...(userId && {
					icon: isMultipleDirectMessageRoom(room) ? <RoomIcon placement='default' room={room} /> : <ReactiveUserStatus uid={userId} />,
				})}
			>
				{roomName}
			</VideoConfPopupInfo>
		);
	}

	return (
		<VideoConfPopupInfo avatar={avatar} icon={<RoomIcon placement='default' room={room} />}>
			{roomName}
		</VideoConfPopupInfo>
	);
};

export default VideoConfPopupRoomInfo;
