import { Box } from '@rocket.chat/fuselage';

import PrivateEmptyStateDefault from './PrivateEmptyStateDefault';

// Zeki: vendor upgrade empty-state removed; private apps are always available
const PrivateEmptyState = () => {
	return (
		<Box mbs='24px'>
			<PrivateEmptyStateDefault />
		</Box>
	);
};

export default PrivateEmptyState;
