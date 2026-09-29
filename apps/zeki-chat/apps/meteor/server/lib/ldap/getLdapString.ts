import type { ILDAPEntry } from '@zeki.chat/core-typings';

export function getLdapString(ldapUser: ILDAPEntry, key: string): string | undefined {
	return ldapUser[key.trim()];
}
