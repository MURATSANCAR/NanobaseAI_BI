// Single point of access to the client-side persistent storage that
// ZEKI AI CHAT shares with Meteor's accounts-base. Reads and writes use
// window.localStorage under the hood; the keys mirror the names Meteor
// originally wrote so sessions persist across the Meteor → SDK migration.
import { Accounts } from 'meteor/accounts-base';

type MeteorLoginKey = 'USER_ID_KEY' | 'LOGIN_TOKEN_KEY' | 'LOGIN_TOKEN_EXPIRES_KEY';

// Zeki: when the app is served under a sub-path (ROOT_URL_PATH_PREFIX, e.g. /timas/sohbet),
// accounts-base namespaces its keys ("Meteor.loginToken:/:/timas/sohbet"). Reading the plain
// names then finds nothing: the REST client sent no X-User-Id / X-Auth-Token, every
// method.call answered 401 and ddpOverREST wiped the fresh session. Use the exact key names
// accounts-base computed; fall back to the plain names only if it is not available.
const meteorLoginKey = (name: MeteorLoginKey, fallback: string): string => {
	try {
		const key = (Accounts as unknown as Partial<Record<MeteorLoginKey, unknown>> | undefined)?.[name];
		return typeof key === 'string' && key ? key : fallback;
	} catch {
		return fallback;
	}
};

export const STORAGE_KEYS = {
	USER_ID: meteorLoginKey('USER_ID_KEY', 'Meteor.userId'),
	LOGIN_TOKEN: meteorLoginKey('LOGIN_TOKEN_KEY', 'Meteor.loginToken'),
	LOGIN_TOKEN_EXPIRES: meteorLoginKey('LOGIN_TOKEN_EXPIRES_KEY', 'Meteor.loginTokenExpires'),
	E2EE_PUBLIC_KEY: 'public_key',
	E2EE_PRIVATE_KEY: 'private_key',
	E2EE_RANDOM_PASSWORD: 'e2e.randomPassword',
} as const;

export type StorageKey = (typeof STORAGE_KEYS)[keyof typeof STORAGE_KEYS];

type StorageBackend = 'local' | 'session';

const getStorageForBackend = (backend: StorageBackend): Storage | undefined => {
	if (typeof window === 'undefined') {
		return undefined;
	}

	try {
		return backend === 'session' ? window.sessionStorage : window.localStorage;
	} catch {
		return undefined;
	}
};

const getStorage = (): Storage | undefined => {
	return getStorageForBackend(storageBackend);
};

export const getStoredItem = (key: StorageKey): string | null => getStorage()?.getItem(key) ?? null;

export const setStoredItem = (key: StorageKey, value: string): void => getStorage()?.setItem(key, value);

export const removeStoredItem = (key: StorageKey): void => getStorage()?.removeItem(key);

let storageBackend: StorageBackend = 'local';

export const setStorageBackend = (backend: StorageBackend): boolean => {
	if (backend === storageBackend) {
		return true;
	}

	if (!moveLoginKeys(backend)) {
		return false;
	}

	storageBackend = backend;
	return true;
};

const moveLoginKeys = (backend: StorageBackend): boolean => {
	const keys = [
		STORAGE_KEYS.USER_ID,
		STORAGE_KEYS.LOGIN_TOKEN,
		STORAGE_KEYS.LOGIN_TOKEN_EXPIRES,
		STORAGE_KEYS.E2EE_PUBLIC_KEY,
		STORAGE_KEYS.E2EE_PRIVATE_KEY,
		STORAGE_KEYS.E2EE_RANDOM_PASSWORD,
	];

	const sourceStorage = getStorageForBackend(backend === 'session' ? 'local' : 'session');
	const targetStorage = getStorageForBackend(backend);

	if (!sourceStorage || !targetStorage) {
		console.warn('Unable to switch storage backend because source or target storage is unavailable');
		return false;
	}

	for (const key of keys) {
		let value: string | null;
		try {
			value = sourceStorage.getItem(key);
		} catch {
			continue;
		}

		if (value === null) {
			continue;
		}

		try {
			targetStorage.setItem(key, value);
			sourceStorage.removeItem(key);
		} catch {
			continue;
		}
	}
	sourceStorage.clear();

	return true;
};
