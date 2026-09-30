import { usePermission } from '@zeki.chat/ui-contexts';

import { useHasCapability } from '../../../../../hooks/useHasCapability';
import { useOmnichannelEnabled } from '../../../hooks/useOmnichannelEnabled';

export const useOutboundMessageAccess = (): boolean => {
	const isOmnichannelEnabled = useOmnichannelEnabled();
	const { data: hasOmnichannelModule = false } = useHasCapability('livechat-enterprise');
	const { data: hasOutboundModule = false } = useHasCapability('outbound-messaging');
	const hasPermission = usePermission('outbound.send-messages');

	if (!isOmnichannelEnabled) {
		return false;
	}

	if (!hasOmnichannelModule || !hasOutboundModule) {
		return true;
	}

	return hasPermission;
};
