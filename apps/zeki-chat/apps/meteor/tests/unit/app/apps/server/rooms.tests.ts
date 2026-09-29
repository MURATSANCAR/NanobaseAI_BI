import type { IAppRoomsConverter, IAppsRoom } from '@zeki.chat/apps';
import type { IRoom } from '@zeki.chat/core-typings';
import { expect } from 'chai';
import { before, describe, it } from 'mocha';
import proxyquire from 'proxyquire';

import { MessagesMock } from './mocks/models/Messages.mock';
import { RoomsMock } from './mocks/models/Rooms.mock';
import { UsersMock } from './mocks/models/Users.mock';
import { AppServerOrchestratorMock } from './mocks/orchestrator.mock';

const { AppRoomsConverter } = proxyquire.noCallThru().load('../../../../../app/apps/server/converters/rooms', {
	'@zeki.chat/random': {
		Random: {
			id: () => 1,
		},
	},
	'@zeki.chat/models': {
		Rooms: new RoomsMock(),
		Messages: new MessagesMock(),
		Users: new UsersMock(),
	},
});

describe('The AppMessagesConverter instance', () => {
	let roomConverter: IAppRoomsConverter;
	let roomsMock: RoomsMock;

	before(() => {
		const orchestrator = new AppServerOrchestratorMock();

		const usersConverter = orchestrator.getConverters().get('users');

		usersConverter.convertById = function convertUserByIdStub(id: string) {
			return UsersMock.convertedData[id as 'zeki.bot'] || undefined;
		};

		usersConverter.convertToApp = function convertUserToAppStub(user: UsersMock['data']['zeki.bot']) {
			return {
				id: user._id,
				username: user.username,
				name: user.name,
			};
		};

		orchestrator.getConverters().get('messages').convertById = async function convertRoomByIdStub(_id: string) {
			return {};
		};

		roomConverter = new AppRoomsConverter(orchestrator);
		roomsMock = new RoomsMock();
	});

	describe('when converting a room from ZEKI AI CHAT to the Engine schema', () => {
		it('should return `undefined` when `originalRoom` is falsy', async () => {
			const appRoom = await roomConverter.convertRoom(undefined);

			expect(appRoom).to.be.undefined;
		});

		it('should return a proper schema', async () => {
			const mockedRoom = roomsMock.findOneById('GENERAL') as RoomsMock['data']['GENERAL'];
			const appRoom = await roomConverter.convertRoom(mockedRoom as unknown as IRoom);

			expect(appRoom).to.have.property('id', mockedRoom._id);
			expect(appRoom).to.have.property('type', mockedRoom.t);
			expect(appRoom).to.have.property('slugifiedName', mockedRoom.name);
			expect(appRoom).to.have.property('createdAt').which.equalTime(mockedRoom.ts);
			expect(appRoom).to.have.property('updatedAt').which.equalTime(mockedRoom._updatedAt);
			expect(appRoom).to.have.property('messageCount', mockedRoom.msgs);
		});

		it('should not mutate the original room object', async () => {
			const zekichatRoomMock = structuredClone(roomsMock.findOneById('GENERAL'));

			await roomConverter.convertRoom(zekichatRoomMock);

			expect(zekichatRoomMock).to.deep.equal(roomsMock.findOneById('GENERAL'));
		});

		it('should add an `_unmappedProperties_` field to the converted room which contains the `lastMessage` property of the room', async () => {
			const mockedRoom = roomsMock.findOneById('GENERAL') as RoomsMock['data']['GENERAL'];
			const appMessage = await roomConverter.convertRoom(mockedRoom as unknown as IRoom);

			expect(appMessage).to.have.property('_unmappedProperties_').which.has.property('lastMessage').to.deep.equal(mockedRoom.lastMessage);
		});
	});

	describe('when converting a room from the Engine schema back to ZEKI AI CHAT', () => {
		it('should return `undefined` when `room` is falsy', async () => {
			const zekichatMessage = await roomConverter.convertAppRoom(undefined);

			expect(zekichatMessage).to.be.undefined;
		});

		it('should return a proper schema', async () => {
			const appRoom = RoomsMock.convertedData.GENERAL as unknown as IAppsRoom;
			const zekichatRoom = await roomConverter.convertAppRoom(appRoom);

			expect(zekichatRoom).to.have.property('_id', appRoom.id);
			expect(zekichatRoom).to.have.property('ts', appRoom.createdAt);
			expect(zekichatRoom).to.have.property('lm', appRoom.lastModifiedAt);
			expect(zekichatRoom).to.have.property('_updatedAt', appRoom.updatedAt);
			expect(zekichatRoom).to.have.property('t', appRoom.type);
			expect(zekichatRoom).to.have.property('name', appRoom.slugifiedName);
		});

		it('should return a proper schema when receiving a partial object', async () => {
			const appRoom = RoomsMock.convertedData.GENERALPartial as unknown as IAppsRoom;
			const zekichatRoom = await roomConverter.convertAppRoom(appRoom, true);

			expect(zekichatRoom).to.have.property('_id', appRoom.id);
			expect(zekichatRoom).to.have.property('name', appRoom.slugifiedName);
			expect(zekichatRoom).to.have.property('sysMes', appRoom.displaySystemMessages);
			expect(zekichatRoom).to.have.property('_updatedAt', appRoom.updatedAt);

			expect(zekichatRoom).to.not.have.property('msgs');
			expect(zekichatRoom).to.not.have.property('ro');
			expect(zekichatRoom).to.not.have.property('default');
			expect(zekichatRoom).to.not.have.property('t');
		});

		it('should return a proper schema when receiving a partial object', async () => {
			const appRoom = RoomsMock.convertedData.GENERALPartialWithOptionalProps as unknown as IAppsRoom;
			const zekichatRoom = await roomConverter.convertAppRoom(appRoom, true);

			expect(zekichatRoom).to.have.property('_id', appRoom.id);
			expect(zekichatRoom).to.have.property('name', appRoom.slugifiedName);
			expect(zekichatRoom).to.have.property('sysMes', appRoom.displaySystemMessages);
			expect(zekichatRoom).to.have.property('_updatedAt', appRoom.updatedAt);
			expect(zekichatRoom).to.have.property('msgs', appRoom.messageCount);
			expect(zekichatRoom).to.have.property('t', 'c');

			expect(zekichatRoom).to.not.have.property('ro');
			expect(zekichatRoom).to.not.have.property('default');
		});

		it('should not include properties that are not present in the app room', async () => {
			const appRoom = RoomsMock.convertedData.UpdatedRoom as unknown as IAppsRoom;
			const zekichatRoom = await roomConverter.convertAppRoom(appRoom, true);

			expect(zekichatRoom).to.have.property('customFields');
			expect(zekichatRoom).to.not.have.property('_id');
			expect(zekichatRoom).to.not.have.property('t');
		});

		it('should not include name as undefined if the room doesnt have a name property', async () => {
			const appRoom = RoomsMock.convertedData.UpdatedRoom as unknown as IAppsRoom;
			const zekichatRoom = await roomConverter.convertAppRoom(appRoom, true);

			expect(zekichatRoom.name).to.be.undefined;
		});

		it('should include a name if the source room has slugifiedName property', async () => {
			const appRoom = RoomsMock.convertedData.GENERALPartialWithOptionalProps as unknown as IAppsRoom;
			const zekichatRoom = await roomConverter.convertAppRoom(appRoom, true);

			expect(zekichatRoom.name).to.equal(appRoom.slugifiedName);
		});

		it('should not use _unmappedProperties when the room is a partial object', async () => {
			const appRoom = RoomsMock.convertedData.GENERALPartialWithOptionalProps as unknown as IAppsRoom;
			// @ts-expect-error - _unmappedProperties
			const zekichatRoom = await roomConverter.convertAppRoom({ ...appRoom, _unmappedProperties_: { unmapped: 'property' } }, true);

			expect(zekichatRoom).to.not.have.property('unmapped');
		});

		it('should use _unmappedProperties when the room is a partial object', async () => {
			const appRoom = RoomsMock.convertedData.GENERALPartialWithOptionalProps as unknown as IAppsRoom;
			// @ts-expect-error - _unmappedProperties
			const zekichatRoom = await roomConverter.convertAppRoom({ ...appRoom, _unmappedProperties_: { unmapped: 'property' } }, false);

			expect(zekichatRoom).to.have.property('unmapped', 'property');
		});
	});
});
