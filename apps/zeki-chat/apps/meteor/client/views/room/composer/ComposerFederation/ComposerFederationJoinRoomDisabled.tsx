import { MessageFooterCallout } from '@zeki.chat/ui-composer';
import type { ReactElement } from 'react';
import { useTranslation } from 'react-i18next';

const ComposerFederationJoinRoomDisabled = (): ReactElement => {
	const { t } = useTranslation();

	return <MessageFooterCallout>{t('Unavailable')}</MessageFooterCallout>;
};

export default ComposerFederationJoinRoomDisabled;
