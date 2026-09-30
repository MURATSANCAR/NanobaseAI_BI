import { Box, Chip, Icon } from '@rocket.chat/fuselage';
import { UserAvatar } from '@zeki.chat/ui-avatar';
import { useUserDisplayName } from '@zeki.chat/ui-client';
import type { ComponentProps } from 'react';

type UserAvatarChipProps = ComponentProps<typeof Chip> & {
	federated?: boolean;
	username: string;
	name?: string;
};

const UserAvatarChip = ({ federated, username, name, ...props }: UserAvatarChipProps) => {
	const displayName = useUserDisplayName({ name, username });
	return (
		<Chip height='x20' {...props}>
			{federated ? <Icon size='x20' name='globe' verticalAlign='middle' /> : <UserAvatar size='x20' username={username} />}
			<Box is='span' margin='none' mis={4} verticalAlign='middle'>
				{displayName}
			</Box>
		</Chip>
	);
};

export default UserAvatarChip;
