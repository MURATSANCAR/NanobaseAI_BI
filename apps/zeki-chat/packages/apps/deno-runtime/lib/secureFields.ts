import { kSecureFields, WithSecureFields } from '@zeki.chat/apps/dist/lib/SecureFields';
import type { App } from '@zeki.chat/apps-engine/definition/App';

import { AppObjectRegistry } from '../AppObjectRegistry.ts';

export type { WithSecureFields } from '@zeki.chat/apps/dist/lib/SecureFields';

export function applySecureFields(object: WithSecureFields<Record<string, unknown>>) {
	const { [kSecureFields]: secureFields, ...rest } = object;

	const app = AppObjectRegistry.get<App>('app');

	if (!app) {
		throw new Error("App unavailable, can't parse object with secure fields");
	}

	secureFields.forEach(({ permission, name, value }) => {
		if (!app.getInfo().permissions?.find((p) => p.name === permission)) {
			return;
		}

		rest[name] = value;
	});

	return rest;
}
