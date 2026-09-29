import { hasCapability } from '../../capabilities/client';

void hasCapability('livechat-enterprise').then((enabled) => {
	if (!enabled) {
		return;
	}

	return Promise.all([import('./views/livechatSideNavItems'), import('./views/business-hours/Multiple')]);
});
