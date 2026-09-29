import { BaseModelMock } from './BaseModel.mock';

export class UsersMock extends BaseModelMock {
	data = {
		'zeki.bot': {
			_id: 'zeki.bot',
			createdAt: new Date('2019-03-27T20:51:36.821Z'),
			avatarOrigin: 'local',
			name: 'ZEKI AI CHAT',
			username: 'zeki.bot',
			status: 'online',
			statusDefault: 'online',
			utcOffset: 0,
			active: true,
			type: 'bot',
			_updatedAt: new Date('2019-03-30T01:11:50.496Z'),
			roles: ['bot'],
		},
	};

	static convertedData = {
		'zeki.bot': {
			id: 'zeki.bot',
			username: 'zeki.bot',
			emails: [
				{
					address: 'rocketcat@rocket.chat',
					verified: true,
				},
			],
			type: 'bot',
			isEnabled: true,
			name: 'ZEKI AI CHAT',
			roles: ['bot'],
			status: 'online',
			statusConnection: 'online',
			utcOffset: 0,
			createdAt: new Date(),
			updatedAt: new Date(),
			lastLoginAt: undefined,
		},
	};
}
