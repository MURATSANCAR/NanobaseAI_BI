import { type ExtendedFetchOptions, Response } from '@zeki.chat/server-fetch';

/**
 * Zeki: the ZEKI AI CHAT Marketplace (marketplace.rocket.chat) is permanently disconnected.
 * This client performs no network request at all: every marketplace endpoint answers locally
 * with an empty/disabled payload, so callers keep working while nothing leaves the workspace.
 */
export class MarketplaceAPIClient {
	public getMarketplaceUrl(): string {
		return '';
	}

	public setStrategy(_strategyName: 'default' | 'mock'): void {
		// no-op: there is only one (offline) strategy
	}

	public fetch(input: string, _options?: ExtendedFetchOptions, _allowSelfSignedCerts?: boolean): Promise<Response> {
		return Promise.resolve(emptyMarketplaceResponse(input));
	}
}

function emptyMarketplaceResponse(input: string): Response {
	let content: string;

	switch (true) {
		case input.includes('v1/featured-apps'):
			content = '{"sections":[]}';
			break;
		case input.includes('v1/app-request/stats'):
			content = '{"data":{"totalSeen":0,"totalUnseen":0}}';
			break;
		case input.includes('v1/app-request/markAsSeen'):
			content = '{"success":false}';
			break;
		case input.includes('v1/app-request'):
			content = '{"data":[],"meta":{"limit":25,"offset":0,"sort":"","filter":"","total":0}}';
			break;
		case input.includes('v1/workspaces'):
			content = '{}';
			break;
		default:
			// v1/apps, v1/categories, v1/bundles and anything else
			content = '[]';
			break;
	}

	return new Response(Buffer.from(content), {
		headers: {
			'content-type': 'application/json',
		},
		status: 200,
	});
}
