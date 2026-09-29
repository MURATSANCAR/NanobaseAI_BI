import type { Path } from '@zeki.chat/rest-typings';

export const APP_URL = 'https://assets.example.invalid/sample';
export const APP_NAME = 'Apps.ZekiChat.Tester';

type PathWithoutPrefix<TPath> = TPath extends `/apps${infer U}` ? U : never;

export function apps(path?: ''): `/api/apps`;
export function apps<TPath extends PathWithoutPrefix<Path>>(path: TPath): `/api/apps${TPath}`;
export function apps(path = '') {
	return `/api/apps${path}` as const;
}

export function installedApps() {
	return `/api/apps/installed` as const;
}
