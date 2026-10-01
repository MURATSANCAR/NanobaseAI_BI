import { isInviteSubscription } from '@zeki.chat/core-typings';
import type { SubscriptionWithRoom } from '@zeki.chat/ui-contexts';

import UnreadBadge from './UnreadBadge';
import InvitationBadge from '../../../../components/InvitationBadge';
import { useUnreadDisplay } from '../hooks/useUnreadDisplay';

type SidebarItemBadgesProps = {
	room: SubscriptionWithRoom;
	roomTitle?: string;
};

const SidebarItemBadges = ({ room, roomTitle }: SidebarItemBadgesProps) => {
	const { unreadCount, unreadTitle, unreadVariant, showUnread } = useUnreadDisplay(room);

	return (
		<>
			{showUnread && <UnreadBadge title={unreadTitle} roomTitle={roomTitle} variant={unreadVariant} total={unreadCount.total} />}
			{isInviteSubscription(room) && <InvitationBadge mbs={2} invitationDate={room.ts} />}
		</>
	);
};

export default SidebarItemBadges;
