import { InfoPanelLabel, InfoPanelText } from '@zeki.chat/ui-client';
import { useTranslation } from 'react-i18next';

import { useHasCapability } from '../../../hooks/useHasCapability';

const MaxChatsPerAgentDisplay = ({ maxNumberSimultaneousChat = 0 }) => {
	const { t } = useTranslation();
	const { data: hasLicense = false } = useHasCapability('livechat-enterprise');

	if (!hasLicense) {
		return null;
	}

	return (
		<>
			<InfoPanelLabel>{t('Max_number_of_chats_per_agent')}</InfoPanelLabel>
			<InfoPanelText>{maxNumberSimultaneousChat}</InfoPanelText>
		</>
	);
};

export default MaxChatsPerAgentDisplay;
