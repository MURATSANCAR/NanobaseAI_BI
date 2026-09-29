import type { IUserBuilder } from '@zeki.chat/apps-engine/definition/accessors/IUserBuilder';
import type { IUser } from '@zeki.chat/apps-engine/definition/users/IUser';
import type { IUserSettings } from '@zeki.chat/apps-engine/definition/users/IUserSettings';
import type { IUserEmail } from '@zeki.chat/apps-engine/definition/users/IUserEmail';
import type { ZekiChatAssociationModel as _ZekiChatAssociationModel } from '@zeki.chat/apps-engine/definition/metadata/ZekiChatAssociations';

import { require } from '../../../lib/require.ts';

const { ZekiChatAssociationModel } = require('@zeki.chat/apps-engine/definition/metadata/ZekiChatAssociations.js') as {
	ZekiChatAssociationModel: typeof _ZekiChatAssociationModel;
};

export class UserBuilder implements IUserBuilder {
	public kind: _ZekiChatAssociationModel.USER;

	private user: Partial<IUser>;

	constructor(user?: Partial<IUser>) {
		this.kind = ZekiChatAssociationModel.USER;
		this.user = user || ({} as Partial<IUser>);
	}

	public setData(data: Partial<IUser>): IUserBuilder {
		delete data.id;
		this.user = data;

		return this;
	}

	public setEmails(emails: Array<IUserEmail>): IUserBuilder {
		this.user.emails = emails;
		return this;
	}

	public getEmails(): Array<IUserEmail> {
		return this.user.emails!;
	}

	public setDisplayName(name: string): IUserBuilder {
		this.user.name = name;
		return this;
	}

	public getDisplayName(): string {
		return this.user.name!;
	}

	public setUsername(username: string): IUserBuilder {
		this.user.username = username;
		return this;
	}

	public getUsername(): string {
		return this.user.username!;
	}

	public setRoles(roles: Array<string>): IUserBuilder {
		this.user.roles = roles;
		return this;
	}

	public getRoles(): Array<string> {
		return this.user.roles!;
	}

	public getSettings(): Partial<IUserSettings> {
		return this.user.settings;
	}

	public getUser(): Partial<IUser> {
		if (!this.user.username) {
			throw new Error('The "username" property is required.');
		}

		if (!this.user.name) {
			throw new Error('The "name" property is required.');
		}

		return this.user;
	}
}
