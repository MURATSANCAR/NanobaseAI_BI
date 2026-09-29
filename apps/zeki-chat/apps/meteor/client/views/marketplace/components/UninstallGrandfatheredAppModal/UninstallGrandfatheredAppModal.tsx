import {
	Button,
	Modal,
	ModalClose,
	ModalContent,
	ModalFooter,
	ModalFooterControllers,
	ModalHeader,
	ModalHeaderText,
	ModalTitle,
} from '@rocket.chat/fuselage';
import { useTranslation } from 'react-i18next';

import MarkdownText from '../../../../components/MarkdownText';
import type { MarketplaceRouteContext } from '../../hooks/useAppsCountQuery';
import { usePrivateAppsEnabled } from '../../hooks/usePrivateAppsEnabled';

type UninstallGrandfatheredAppModalProps = {
	context: MarketplaceRouteContext;
	limit: number;
	appName: string;
	handleUninstall: () => void;
	handleClose: () => void;
};

const UninstallGrandfatheredAppModal = ({ context, limit, appName, handleUninstall, handleClose }: UninstallGrandfatheredAppModalProps) => {
	const { t } = useTranslation();
	const privateAppsEnabled = usePrivateAppsEnabled();

	const modalContent =
		context === 'private' && !privateAppsEnabled
			? t('App_will_lose_grandfathered_status_private')
			: t('App_will_lose_grandfathered_status', { limit });

	return (
		<Modal>
			<ModalHeader>
				<ModalHeaderText>
					<ModalTitle>{t('Uninstall_grandfathered_app', { appName })}</ModalTitle>
				</ModalHeaderText>
				<ModalClose onClick={handleClose} />
			</ModalHeader>
			<ModalContent>
				<MarkdownText content={modalContent} />
			</ModalContent>
			<ModalFooter justifyContent='space-between'>
				<ModalFooterControllers>
					<Button onClick={handleClose}>{t('Cancel')}</Button>
					<Button danger onClick={handleUninstall}>
						{t('Uninstall')}
					</Button>
				</ModalFooterControllers>
			</ModalFooter>
		</Modal>
	);
};

export default UninstallGrandfatheredAppModal;
