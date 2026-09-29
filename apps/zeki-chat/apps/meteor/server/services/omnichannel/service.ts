import { ServiceClassInternal } from '@zeki.chat/core-services';
import type { IOmnichannelService } from '@zeki.chat/core-services';
import type { IOmnichannelQueue } from '@zeki.chat/core-typings';
import { Capabilities } from '@zeki.chat/capabilities';

import { OmnichannelQueue } from './queue';
import { RoutingManager } from '../../../app/livechat/server/lib/RoutingManager';
import { notifyAgentStatusChanged } from '../../../app/livechat/server/lib/omni-users';
import { settings } from '../../../app/settings/server';

export class OmnichannelService extends ServiceClassInternal implements IOmnichannelService {
	protected name = 'omnichannel';

	private queueWorker: IOmnichannelQueue;

	constructor() {
		super();
		this.queueWorker = new OmnichannelQueue();
	}

	override async created() {
		this.onEvent('presence.status', async ({ user }): Promise<void> => {
			if (!user?._id) {
				return;
			}
			const hasRole = user.roles.some((role) => ['livechat-manager', 'livechat-monitor', 'livechat-agent'].includes(role));
			if (hasRole) {
				// TODO change `Livechat.notifyAgentStatusChanged` to a service call
				await notifyAgentStatusChanged(user._id, user.status);
			}
		});
	}

	override async started() {
		settings.watchMultiple(['Livechat_enabled', 'Livechat_Routing_Method'], () => {
			this.queueWorker.shouldStart();
		});


		Capabilities.onReady(async (): Promise<void> => {
			RoutingManager.isMethodSet() && (await this.queueWorker.shouldStart());
		});

	}

}
