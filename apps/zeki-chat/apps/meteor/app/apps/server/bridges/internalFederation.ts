import type { IInternalFederationBridge } from '@zeki.chat/apps/dist/server/bridges/IInternalFederationBridge';
import { FederationKeys } from '@zeki.chat/models';

export class AppInternalFederationBridge implements IInternalFederationBridge {
	async getPrivateKey(): Promise<string | null> {
		return FederationKeys.getKey('private');
	}

	async getPublicKey(): Promise<string | null> {
		return FederationKeys.getKey('public');
	}
}
