import type { IUpload } from '@zeki.chat/core-typings';
import { useEffectEvent } from '@rocket.chat/fuselage-hooks';
import { GenericModal } from '@zeki.chat/ui-client';
import { useSetModal, useToastMessageDispatch, useMethod } from '@zeki.chat/ui-contexts';
import { useTranslation } from 'react-i18next';

export const useDeleteFile = (reload: () => void) => {
	const { t } = useTranslation();
	const setModal = useSetModal();
	const dispatchToastMessage = useToastMessageDispatch();
	const deleteFile = useMethod('deleteFileMessage');

	const handleDelete = useEffectEvent((_id: IUpload['_id']) => {
		const onConfirm = async () => {
			try {
				await deleteFile(_id);
				dispatchToastMessage({ type: 'success', message: t('Deleted') });
				reload();
			} catch (error) {
				dispatchToastMessage({ type: 'error', message: error });
			} finally {
				setModal(null);
			}
		};

		setModal(
			<GenericModal variant='danger' onConfirm={onConfirm} onCancel={() => setModal(null)} confirmText={t('Delete')}>
				{t('Delete_File_Warning')}
			</GenericModal>,
		);
	});

	return handleDelete;
};
