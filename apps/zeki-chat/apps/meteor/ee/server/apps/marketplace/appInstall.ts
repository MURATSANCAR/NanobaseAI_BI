import type { IAppInfo } from '@rocket.chat/apps-engine/definition/metadata';


type MarketplaceNotificationType = 'install' | 'update' | 'uninstall';

/**
 * Notify the marketplace about an app install, update, or uninstall event.
 *
 * Attempts to POST a notification to the marketplace client at `v1/apps/{id}/install` containing the action, app metadata, Rocket.Chat and engine versions, and site URL. If a workspace access token is available it is included in the Authorization header. Any errors encountered while obtaining the token, reading settings, or sending the request are ignored.
 *
 * @param action - The marketplace event type: 'install', 'update', or 'uninstall'
 * @param appInfo - App metadata (including `id`, `name`, `nameSlug`, and `version`) to include in the notification
 */
// Zeki: install/update/uninstall events are never reported to marketplace.rocket.chat.
export async function notifyMarketplace(_action: MarketplaceNotificationType, _appInfo: IAppInfo): Promise<void> {
	// no-op
}
