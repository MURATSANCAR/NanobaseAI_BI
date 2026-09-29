import type { IRoom, ISubscription, IMessage } from '@zeki.chat/core-typings';

import JumpToMessageAction from './actions/JumpToMessageAction';

type PinnedItemsProps = {
	message: IMessage;
	room: IRoom;
	subscription: ISubscription | undefined;
};

const PinnedItems = ({ message }: PinnedItemsProps) => {
	return (
		<>
			<JumpToMessageAction id='jump-to-pin-message' message={message} />
		</>
	);
};

export default PinnedItems;
