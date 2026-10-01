import type { IRoom } from '@zeki.chat/core-typings';
import { HeaderState } from '@zeki.chat/ui-client';
import { useSetting } from '@zeki.chat/ui-contexts';
import { memo } from 'react';
import { useTranslation } from 'react-i18next';

type TranslateProps = {
	room: IRoom;
};

const Translate = ({ room: { autoTranslateLanguage, autoTranslate } }: TranslateProps) => {
	const { t } = useTranslation();
	const autoTranslateEnabled = useSetting('AutoTranslate_Enabled');
	const encryptedLabel = t('Translated');
	return autoTranslateEnabled && autoTranslate && autoTranslateLanguage ? (
		<HeaderState title={encryptedLabel} icon='language' color='info' />
	) : null;
};

export default memo(Translate);
