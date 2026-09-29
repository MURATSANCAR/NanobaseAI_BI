import { Box } from '@rocket.chat/fuselage';
import { MessageComposerSkeleton } from '@zeki.chat/ui-composer';

const ComposerSkeleton = () => {
	return (
		<>
			<MessageComposerSkeleton />
			<Box height='x24' />
		</>
	);
};

export default ComposerSkeleton;
