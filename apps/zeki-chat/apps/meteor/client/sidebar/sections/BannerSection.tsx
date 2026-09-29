import { useSessionStorage } from '@rocket.chat/fuselage-hooks';
import { useSetting } from '@zeki.chat/ui-contexts';

import StatusDisabledBanner from './StatusDisabledBanner';

const BannerSection = () => {

	const [bannerDismissed, setBannerDismissed] = useSessionStorage('presence_cap_notifier', false);
	const presenceDisabled = useSetting('Presence_broadcast_disabled', false);

	if (presenceDisabled && !bannerDismissed) {
		return <StatusDisabledBanner onDismiss={() => setBannerDismissed(true)} />;
	}

	return null;
};

export default BannerSection;
