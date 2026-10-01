import { Box } from '@rocket.chat/fuselage';
import { Trans } from 'react-i18next';

const NewBot = () => (
	<Box pb={20} fontScale='h4' key='bots'>
		<Trans
			i18nKey='additional_integrations_Bots'
			components={{ a: <span /> }} // Zeki: vendor bot repository link removed
		/>
	</Box>
);

export default NewBot;
