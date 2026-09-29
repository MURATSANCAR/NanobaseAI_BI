import type { IRoom } from '@zeki.chat/core-typings';
import { isOmnichannelRoom } from '@zeki.chat/core-typings';
import { HeaderIcon } from '@zeki.chat/ui-client';
import type { ReactElement } from 'react';

import { OmnichannelRoomIcon } from '../../../components/RoomIcon/OmnichannelRoomIcon';
import { useRoomIcon } from '../../../hooks/useRoomIcon';

type HeaderIconWithRoomProps = {
	room: IRoom;
};

const HeaderIconWithRoom = ({ room }: HeaderIconWithRoomProps): ReactElement => {
	const icon = useRoomIcon(room);
	if (isOmnichannelRoom(room)) {
		return <OmnichannelRoomIcon source={room.source} status={room.v?.status} size='x20' />;
	}

	return <HeaderIcon icon={icon} />;
};

export default HeaderIconWithRoom;
