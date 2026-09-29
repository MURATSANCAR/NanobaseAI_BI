import type { IWorkspaceInfo } from '@rocket.chat/core-typings';
import { Card, CardCol, CardHeader, CardTitle } from '@rocket.chat/fuselage';
import type { ReactElement } from 'react';
import { useTranslation } from 'react-i18next';

type VersionCardProps = { serverInfo: IWorkspaceInfo };
const VersionCard = ({ serverInfo }: VersionCardProps): ReactElement => {
	const { t } = useTranslation();
	return <Card><CardCol><CardHeader><CardTitle variant='h3'>{t('Version_version', { version: serverInfo.version })}</CardTitle></CardHeader></CardCol></Card>;
};
export default VersionCard;
