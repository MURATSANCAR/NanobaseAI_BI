import { Users } from '@zeki.chat/models';

import { settings } from '../../../settings/server';

// Zeki: the workspace is never registered with ZEKI AI CHAT Cloud, regardless of stored settings.
export async function retrieveRegistrationStatus(): Promise<{
	workspaceRegistered: boolean;
	workspaceId: string;
	uniqueId: string;
	token: string;
	email: string;
}> {
	const info = {
		workspaceRegistered: false,
		workspaceId: '',
		uniqueId: settings.get<string>('uniqueID'),
		token: '',
		email: settings.get<string>('Organization_Email') || '',
	};

	if (!info.email) {
		const firstUser = await Users.getOldest({ projection: { emails: 1 } });
		info.email = firstUser?.emails?.[0]?.address || info.email;
	}

	return info;
}
