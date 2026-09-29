/** Sessions expire or are revoked explicitly; opening another device never evicts an existing session. */
export function getMaxLoginTokens(): number {
	return Number.POSITIVE_INFINITY;
}
