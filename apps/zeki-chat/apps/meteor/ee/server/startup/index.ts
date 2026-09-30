import '../../app/authorization/server';
import './audit';
import './deviceManagement';
import './engagementDashboard';
import './services';
import './readReceiptsArchive';
import { api } from '@zeki.chat/core-services';

import { isRunningMs } from '../../../server/lib/isRunningMs';

export const registerEEBroker = async (): Promise<void> => {
	// only starts network broker if running in micro services mode
	if (isRunningMs()) {
		const { startBroker } = await import('@zeki.chat/network-broker');

		api.setBroker(startBroker());
		await api.start();
	} else {
		require('./presence');
	}
};
