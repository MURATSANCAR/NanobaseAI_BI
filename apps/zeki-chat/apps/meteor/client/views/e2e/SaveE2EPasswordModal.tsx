import { Box, CodeSnippet } from '@rocket.chat/fuselage';
import { useClipboard } from '@rocket.chat/fuselage-hooks';
import { GenericModal } from '@zeki.chat/ui-client';
import { useId, type ReactElement } from 'react';
import { useTranslation } from 'react-i18next';


type SaveE2EPasswordModalProps = {
	randomPassword: string;
	onClose: () => void;
	onCancel: () => void;
	onConfirm: () => void;
};

const SaveE2EPasswordModal = ({ randomPassword, onClose, onCancel, onConfirm }: SaveE2EPasswordModalProps): ReactElement => {
	const { t } = useTranslation();
	const { copy, hasCopied } = useClipboard(randomPassword);
	const passwordId = useId();

	return (
		<GenericModal
			onClose={onClose}
			onCancel={onCancel}
			onConfirm={onConfirm}
			cancelText={t('Do_It_Later')}
			confirmText={t('I_Saved_My_Password')}
			variant='warning'
			title={t('Save_your_new_E2EE_password')}
			annotation={t('You_can_do_from_account_preferences')}
		>
			<p>
				{/* Zeki: vendor E2EE guide link removed */}
				{t('E2E_password_reveal_text')}
			</p>
			<Box is='p' fontWeight='bold' mb={20}>
				{t('E2E_password_save_text')}
			</Box>
			<p id={passwordId}>{t('Your_E2EE_password_is')}</p>
			<CodeSnippet
				aria-labelledby={passwordId}
				buttonText={hasCopied ? t('Copied') : t('Copy')}
				buttonDisabled={hasCopied}
				onClick={() => copy()}
				mbs={8}
			>
				{randomPassword}
			</CodeSnippet>
		</GenericModal>
	);
};

export default SaveE2EPasswordModal;
