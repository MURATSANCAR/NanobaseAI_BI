import { Meteor } from 'meteor/meteor';
import type { ServerMethods } from '@zeki.chat/ddp-client';
import { Users } from '@zeki.chat/models';
import { isPersonalAccessToken } from '@zeki.chat/core-typings';

import { hasPermissionAsync } from '../../../../../app/authorization/server/functions/hasPermission';
import { twoFactorRequired } from '../../../../../app/2fa/server/twoFactorRequired';
import { removePersonalAccessTokenOfUser } from './removeToken';
import { generatePersonalAccessTokenOfUser } from './generateToken';

declare module '@zeki.chat/ddp-client' {
	// eslint-disable-next-line @typescript-eslint/naming-convention
	interface ServerMethods {
		'personalAccessTokens:regenerateToken'(params: { tokenName: string }): Promise<string>;
	}
}

export const regeneratePersonalAccessTokenOfUser = async (tokenName: string, userId: string): Promise<string> => {
	if (!(await hasPermissionAsync(userId, 'create-personal-access-tokens'))) {
		throw new Meteor.Error('not-authorized', 'Not Authorized', {
			method: 'personalAccessTokens:regenerateToken',
		});
	}

	const tokenExist = await Users.findPersonalAccessTokenByTokenNameAndUserId({
		userId,
		tokenName,
	});
	if (!tokenExist) {
		throw new Meteor.Error('error-token-does-not-exists', 'Token does not exist', {
			method: 'personalAccessTokens:regenerateToken',
		});
	}

	await removePersonalAccessTokenOfUser(tokenName, userId);

	const tokenObject = tokenExist.services?.resume?.loginTokens?.find((token) => isPersonalAccessToken(token) && token.name === tokenName);

	return generatePersonalAccessTokenOfUser({
		tokenName,
		userId,
		bypassTwoFactor: (tokenObject && isPersonalAccessToken(tokenObject) && tokenObject.bypassTwoFactor) || false,
	});
};

Meteor.methods<ServerMethods>({
	'personalAccessTokens:regenerateToken': twoFactorRequired(async function ({ tokenName }: { tokenName: string }) {
		const uid = Meteor.userId();
		if (!uid) {
			throw new Meteor.Error('not-authorized', 'Not Authorized', {
				method: 'personalAccessTokens:regenerateToken',
			});
		}

		return regeneratePersonalAccessTokenOfUser(tokenName, uid);
	}),
});
