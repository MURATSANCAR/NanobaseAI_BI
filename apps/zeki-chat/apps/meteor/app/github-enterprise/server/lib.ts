import type { OauthConfig } from '@zeki.chat/core-typings';
import { Meteor } from 'meteor/meteor';

import { CustomOAuth } from '../../custom-oauth/server/custom_oauth_server';
import { settings } from '../../settings/server';

// GitHub Enterprise Server CallBack URL needs to be http(s)://{zekichat.server}[:port]/_oauth/github_enterprise
// In ZekiChat -> Administration the URL needs to be http(s)://{github.enterprise.server}/

const config: OauthConfig = {
	serverURL: '',
	identityPath: '/api/v3/user',
	authorizePath: '/login/oauth/authorize',
	tokenPath: '/login/oauth/access_token',
	addAutopublishFields: {
		forLoggedInUser: ['services.github-enterprise'],
		forOtherUsers: ['services.github-enterprise.username'],
	},
};

const GitHubEnterprise = new CustomOAuth('github_enterprise', config);

Meteor.startup(() => {
	settings.watch<string>('API_GitHub_Enterprise_URL', (value) => {
		config.serverURL = value;
		GitHubEnterprise.configure(config);
	});
});
