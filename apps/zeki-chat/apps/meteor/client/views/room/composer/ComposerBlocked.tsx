import { MessageFooterCallout } from '@zeki.chat/ui-composer';
import type { ReactElement } from 'react';
import { useTranslation } from 'react-i18next';

const ComposerBlocked = (): ReactElement => {
	const { t } = useTranslation();
	return <MessageFooterCallout>{t('room_is_blocked')}</MessageFooterCallout>;
};

export default ComposerBlocked;
