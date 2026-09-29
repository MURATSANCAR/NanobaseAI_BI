import { Button, ButtonGroup } from '@rocket.chat/fuselage';
import { ContextualbarScrollableContent, ContextualbarFooter, ContextualbarEmptyContent } from '@rocket.chat/ui-client';
import { useRouter } from '@rocket.chat/ui-contexts';
import { useTranslation } from 'react-i18next';

// Zeki: the vendor "Buy more seats" checkout button was removed; this is now a plain notice.
const AdminUserUpgrade = () => {
	const { t } = useTranslation();
	const router = useRouter();

	return (
		<>
			<ContextualbarScrollableContent h='full'>
				<ContextualbarEmptyContent icon='warning' title={t('Seat_limit_reached')} subtitle={t('Seat_limit_reached_Description')} />
			</ContextualbarScrollableContent>
			<ContextualbarFooter>
				<ButtonGroup stretch>
					<Button onClick={() => router.navigate('/admin/users')}>{t('Cancel')}</Button>
				</ButtonGroup>
			</ContextualbarFooter>
		</>
	);
};

export default AdminUserUpgrade;
