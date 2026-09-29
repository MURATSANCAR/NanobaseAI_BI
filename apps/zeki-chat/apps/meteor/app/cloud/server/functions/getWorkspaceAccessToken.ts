/**
 * Zeki: Rocket.Chat Cloud is permanently disconnected.
 * There is no workspace registration and no access token is ever requested from cloud services.
 * These exports are kept only so existing callers compile; they never perform network calls.
 */

export async function getWorkspaceAccessToken(_forceNew = false, _scope = '', _save = true, _throwOnError = false): Promise<string> {
	return '';
}

export class CloudWorkspaceAccessTokenError extends Error {
	constructor() {
		super('Could not get workspace access token');
	}
}

export const isAbortError = (error: unknown): error is { type: 'AbortError' } => {
	if (typeof error !== 'object' || error === null) {
		return false;
	}

	return 'type' in error && error.type === 'AbortError';
};

export class CloudWorkspaceAccessTokenEmptyError extends Error {
	constructor() {
		super('Workspace access token is empty');
	}
}

export async function getWorkspaceAccessTokenOrThrow(_forceNew = false, _scope = '', _save = true): Promise<string> {
	throw new CloudWorkspaceAccessTokenEmptyError();
}

export const generateWorkspaceBearerHttpHeaderOrThrow = async (
	_forceNew = false,
	_scope = '',
	_save = true,
): Promise<{ Authorization: string }> => {
	throw new CloudWorkspaceAccessTokenEmptyError();
};

export const generateWorkspaceBearerHttpHeader = async (
	_forceNew = false,
	_scope = '',
	_save = true,
): Promise<{ Authorization: string } | undefined> => undefined;
