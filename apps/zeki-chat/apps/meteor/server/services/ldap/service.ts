import type { ILDAPService } from '@zeki.chat/core-services';
import { ServiceClassInternal } from '@zeki.chat/core-services';
import type { LDAPLoginResult } from '@zeki.chat/core-typings';

import { LDAPManager } from '../../lib/ldap/Manager';

export class LDAPService extends ServiceClassInternal implements ILDAPService {
	protected name = 'ldap';

	async loginRequest(username: string, password: string): Promise<LDAPLoginResult> {
		return LDAPManager.login(username, password);
	}

	async loginAuthenticatedUserRequest(username: string): Promise<LDAPLoginResult> {
		return LDAPManager.loginAuthenticatedUser(username);
	}

	async testConnection(): Promise<void> {
		return LDAPManager.testConnection();
	}

	async testSearch(username: string): Promise<void> {
		return LDAPManager.testSearch(username);
	}
}
