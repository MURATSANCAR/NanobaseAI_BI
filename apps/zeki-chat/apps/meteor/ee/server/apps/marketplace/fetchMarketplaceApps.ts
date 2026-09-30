import type { App } from '@zeki.chat/core-typings';

type FetchMarketplaceAppsParams = {
	endUserID?: string;
};

// This local installation has no external application catalog.
export async function fetchMarketplaceApps(_params: FetchMarketplaceAppsParams = {}): Promise<App[]> {
	return [];
}
