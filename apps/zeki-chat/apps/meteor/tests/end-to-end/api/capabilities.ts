import type { Credentials } from '@zeki.chat/api-client';
import type { IUser } from '@zeki.chat/core-typings';
import { expect } from 'chai';
import { before, describe, it, after } from 'mocha';

import { getCredentials, api, request, credentials } from '../../data/api-data';
import { password } from '../../data/user';
import type { TestUser } from '../../data/users.helper';
import { createUser, deleteUser, login } from '../../data/users.helper';

describe('capabilities', () => {
	let createdUser: TestUser<IUser>;

	before((done) => getCredentials(done));
	let unauthorizedUserCredentials: Credentials;

	before(async () => {
		createdUser = await createUser();
		unauthorizedUserCredentials = await login(createdUser.username, password);
	});

	after(() => deleteUser(createdUser));

	describe('[/capabilities.info]', () => {
		it('should fail if not logged in', (done) => {
			void request
				.get(api('capabilities.info'))
				.expect('Content-Type', 'application/json')
				.expect(401)
				.expect((res) => {
					expect(res.body).to.have.property('status', 'error');
					expect(res.body).to.have.property('message');
				})
				.end(done);
		});

		it('should return local modules for an authenticated ordinary user', (done) => {
			void request
				.get(api('capabilities.info'))
				.set(unauthorizedUserCredentials)
				.expect('Content-Type', 'application/json')
				.expect(200)
				.expect((res) => {
					expect(res.body).to.have.property('success', true);
					expect(res.body.capabilities).to.have.all.keys('modules');
					expect(res.body.capabilities.modules).to.be.an('array');
					expect(res.body.capabilities.modules).to.include('custom-roles');
				})
				.end(done);
		});

		it('should return local modules for an administrator', (done) => {
			void request
				.get(api('capabilities.info'))
				.set(credentials)
				.expect(200)
				.expect((res) => {
					expect(res.body).to.have.property('success', true);
					expect(res.body.capabilities).to.have.all.keys('modules');
					expect(res.body.capabilities.modules).to.be.an('array');
					expect(res.body.capabilities.modules).to.include('custom-roles');
				})

				.end(done);
		});
	});
});
