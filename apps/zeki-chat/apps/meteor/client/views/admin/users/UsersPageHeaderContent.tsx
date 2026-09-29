import { Button, ButtonGroup } from '@rocket.chat/fuselage';
import { usePermission, useRouter } from '@zeki.chat/ui-contexts';
import { useTranslation } from 'react-i18next';

const UsersPageHeaderContent = () => {
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
			<ButtonGroup>
				{canBulkCreateUser && (
					<Button icon='mail' onClick={handleInviteButtonClick}>
						{t('Invite')}
					</Button>
				)}

				{canCreateUser && (
					<Button icon='user-plus' onClick={handleNewButtonClick}>
						{t('New_user')}
					</Button>
				)}

				{/* Zeki: vendor 'Buy more seats' checkout button removed */}
			</ButtonGroup>
		</>
	);
};

export default UsersPageHeaderContent;
