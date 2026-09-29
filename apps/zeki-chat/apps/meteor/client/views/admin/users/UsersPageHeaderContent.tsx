import { Button, ButtonGroup, Margins } from '@rocket.chat/fuselage';
import { usePermission, useRouter } from '@rocket.chat/ui-contexts';
import { useTranslation } from 'react-i18next';

import SeatsCapUsage from './SeatsCapUsage';
import type { SeatCapProps } from './useSeatsCap';

type UsersPageHeaderContentProps = {
	isSeatsCapExceeded: boolean;
	seatsCap?: Omit<SeatCapProps, 'reload'>;
};

const UsersPageHeaderContent = ({ isSeatsCapExceeded, seatsCap }: UsersPageHeaderContentProps) => {
	const { t } = useTranslation();
	const router = useRouter();
	const canCreateUser = usePermission('create-user');
	const canBulkCreateUser = usePermission('bulk-register-user');

	const handleNewButtonClick = () => {
		router.navigate('/admin/users/new');
	};

	const handleInviteButtonClick = () => {
		router.navigate('/admin/users/invite');
	};

	return (
		<>
			{seatsCap && seatsCap.maxActiveUsers < Number.POSITIVE_INFINITY && (
				<Margins inline={16}>
					<SeatsCapUsage members={seatsCap.activeUsers} limit={seatsCap.maxActiveUsers} />
				</Margins>
			)}
			<ButtonGroup>
				{canBulkCreateUser && (
					<Button icon='mail' onClick={handleInviteButtonClick} disabled={isSeatsCapExceeded}>
						{t('Invite')}
					</Button>
				)}

				{canCreateUser && (
					<Button icon='user-plus' onClick={handleNewButtonClick} disabled={isSeatsCapExceeded}>
						{t('New_user')}
					</Button>
				)}

				{/* Zeki: vendor 'Buy more seats' checkout button removed */}
			</ButtonGroup>
		</>
	);
};

export default UsersPageHeaderContent;
