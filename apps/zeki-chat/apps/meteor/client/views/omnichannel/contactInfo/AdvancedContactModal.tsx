import { GenericModal } from '@zeki.chat/ui-client';
import { useTranslation } from 'react-i18next';

type AdvancedContactModalProps = {
	onCancel: () => void;
};

// Zeki: was a vendor plan upsell modal (hero image, "Upgrade"/checkout link, telemetry).
// Reduced to a neutral notice that the capability is unavailable on this workspace.
const AdvancedContactModal = ({ onCancel }: AdvancedContactModalProps) => {
	const { t } = useTranslation();

	return (
		<GenericModal
			variant='info'
			title={t('Advanced_contact_profile')}
			confirmText={t('Close')}
			onConfirm={onCancel}
			onClose={onCancel}
		>
			{t('Advanced_contact_profile_description')}
		</GenericModal>
	);
};

export default AdvancedContactModal;
