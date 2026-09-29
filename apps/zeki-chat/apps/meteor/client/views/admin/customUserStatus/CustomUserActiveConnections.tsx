import { Box, Skeleton } from '@rocket.chat/fuselage';
import { useTranslation } from 'react-i18next';

import { useActiveConnections } from '../../hooks/useActiveConnections';

const CustomUserActiveConnections = () => {
	const { t } = useTranslation();
	const result = useActiveConnections();
	if (!result.isSuccess) return <Skeleton />;
	return <Box>{t('Active_connections')}: {result.data.current}</Box>;
};
export default CustomUserActiveConnections;
