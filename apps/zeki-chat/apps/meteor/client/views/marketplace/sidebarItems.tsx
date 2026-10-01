// Zeki: Explore / Premium / Requested tabs and the vendor documentation link removed.
import { hasAtLeastOnePermission, hasPermission } from '../../../app/authorization/client';
import { createSidebarItems } from '../../lib/createSidebarItems';

export const {
	registerSidebarItem: registerMarketplaceSidebarItem,
	unregisterSidebarItem: unregisterMarketplaceSidebarItem,
	getSidebarItems: getMarketplaceSidebarItems,
	subscribeToSidebarItems: subscribeToMarketplaceSidebarItems,
} = createSidebarItems([
	{
		href: '/marketplace/installed',
		icon: 'circle-arrow-down',
		i18nLabel: 'Installed',
		permissionGranted: (): boolean => hasAtLeastOnePermission(['access-marketplace', 'manage-apps']),
	},
	{
		href: '/marketplace/private',
		icon: 'lock',
		i18nLabel: 'Private_Apps',
		permissionGranted: (): boolean => hasAtLeastOnePermission(['access-marketplace', 'manage-apps']),
	},
	{ divider: true, i18nLabel: 'marketplace/private', permissionGranted: (): boolean => hasPermission('access-marketplace') },
]);
