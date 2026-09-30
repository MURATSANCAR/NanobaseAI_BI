import {
	Modal,
	Button,
	Box,
	Callout,
	ModalHeader,
	ModalHeaderText,
	ModalTagline,
	ModalTitle,
	ModalClose,
	ModalContent,
	ModalHeroImage,
	ModalFooter,
	ModalFooterAnnotation,
	ModalFooterControllers,
} from '@rocket.chat/fuselage';
import type { ReactElement } from 'react';
import { useTranslation } from 'react-i18next';

type VideoConfConfigModalProps = {
	onClose: () => void;
	onConfirm?: () => void;
	isAdmin: boolean;
};

const VideoConfConfigModal = ({ onClose, onConfirm, isAdmin }: VideoConfConfigModalProps): ReactElement => {
	const { t } = useTranslation();

	return (
		<Modal>
			<ModalHeader>
				<ModalHeaderText>
					<ModalTagline>{isAdmin ? t('Missing_configuration') : t('App_not_enabled')}</ModalTagline>
					<ModalTitle>{isAdmin ? t('Configure_video_conference') : t('Video_Conference')}</ModalTitle>
				</ModalHeaderText>
				<ModalClose title={t('Close')} onClick={onClose} />
			</ModalHeader>
			<ModalContent>
				<ModalHeroImage maxHeight='initial' src='/images/conf-call-config.svg' />
				<Box fontScale='h3' mbs={24}>
					{t('Required_action')}
				</Box>
				<Callout mbs={12} mbe={24} title={t('Missing_configuration')} type='warning'>
					{isAdmin
						? t('An_app_needs_to_be_installed_and_configured')
						: t('A_workspace_admin_needs_to_install_and_configure_a_conference_call_app')}
				</Callout>
			</ModalContent>
			<ModalFooter justifyContent='space-between'>
				<ModalFooterAnnotation>
					{isAdmin
						? t('Configure_video_conference_to_make_it_available_on_this_workspace')
						: t('Talk_to_your_workspace_administrator_about_enabling_video_conferencing')}
				</ModalFooterAnnotation>
				<ModalFooterControllers>
					<Button onClick={onClose}>{t('Close')}</Button>
					{onConfirm && isAdmin && (
						<Button primary onClick={onConfirm}>
							{t('Open_settings')}
						</Button>
					)}
				</ModalFooterControllers>
			</ModalFooter>
		</Modal>
	);
};

export default VideoConfConfigModal;
