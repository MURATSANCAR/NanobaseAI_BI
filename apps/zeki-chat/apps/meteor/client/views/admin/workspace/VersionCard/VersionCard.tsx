import type { IWorkspaceInfo } from '@rocket.chat/core-typings';
import { Box, Card, CardBody, CardCol, CardHeader, CardTitle } from '@rocket.chat/fuselage';
import { useBreakpoints } from '@rocket.chat/fuselage-hooks';
import { useLicense, useLicenseName } from '@rocket.chat/ui-client';
import { useMediaUrl } from '@rocket.chat/ui-contexts';
import type { ReactElement } from 'react';
import { useMemo } from 'react';
import { useTranslation } from 'react-i18next';

import type { VersionActionItem } from './components/VersionCardActionItem';
import VersionCardActionItem from './components/VersionCardActionItem';
import { VersionCardSkeleton } from './components/VersionCardSkeleton';
import { isOverLicenseLimits } from '../../../../lib/utils/isOverLicenseLimits';

/**
 * Zeki: workspace registration, cloud supported-versions checks and the external
 * "update product" link were removed; this card only shows local information.
 */
type VersionCardProps = {
	serverInfo: IWorkspaceInfo;
};

const VersionCard = ({ serverInfo }: VersionCardProps): ReactElement => {
	const breakpoints = useBreakpoints();
	const isExtraLargeOrBigger = breakpoints.includes('xl');

	const getUrl = useMediaUrl();
	const cardBackground = {
		backgroundImage: `url(${getUrl('images/globe.png')})`,
		backgroundRepeat: 'no-repeat',
		backgroundPosition: isExtraLargeOrBigger ? 'right 20px center' : 'left 450px center',
		backgroundSize: 'auto',
	};

	const { t } = useTranslation();

	const { data: licenseData, isPending } = useLicense({ loadValues: true });
	const { limits } = licenseData || {};
	const licenseName = useLicenseName();

	const serverVersion = serverInfo.version;

	const isOverLimits = limits && isOverLicenseLimits(limits);

	const actionItems = useMemo(
		() =>
			[
				isOverLimits
					? {
							danger: true,
							icon: 'warning',
							label: t('Plan_limits_reached'),
						}
					: {
							icon: 'check',
							label: t('Operating_withing_plan_limits'),
						},
			].filter(Boolean) as VersionActionItem[],
		[isOverLimits, t],
	);

	if (isPending && !licenseData) {
		return (
			<Card style={{ ...cardBackground }}>
				<VersionCardSkeleton />
			</Card>
		);
	}

	return (
		<Card style={{ ...cardBackground }}>
			<CardCol>
				<CardHeader>
					<CardTitle variant='h3'>{t('Version_version', { version: serverVersion })}</CardTitle>
				</CardHeader>

				<Box color='secondary-info'>
					{/* Zeki: vendor logo glyph removed */}
					{licenseName.data}
				</Box>
			</CardCol>

			<CardBody flexDirection='column'>
				{actionItems.length > 0 && actionItems.map((item, index) => <VersionCardActionItem key={index} {...item} />)}
			</CardBody>
		</Card>
	);
};

export default VersionCard;
