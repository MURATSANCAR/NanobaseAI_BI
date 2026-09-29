import { MessageFooterCallout, MessageFooterCalloutContent } from '@zeki.chat/ui-composer';
import type { ReactElement } from 'react';
import { useTranslation } from 'react-i18next';

const ComposerReadOnly = (): ReactElement => {
	const { t } = useTranslation();

	return (
		<MessageFooterCallout>
			<MessageFooterCalloutContent>{t('Room_archived')}</MessageFooterCalloutContent>
		</MessageFooterCallout>
	);
};

export default ComposerReadOnly;
