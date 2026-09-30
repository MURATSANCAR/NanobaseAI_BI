import { expect } from 'chai';
import { before, after, describe, it } from 'mocha';
import type { Response } from 'supertest';

import { getCredentials, api, request, credentials } from '../../data/api-data';
import { updatePermission } from '../../data/permissions.helper';

describe('LDAP', function () {
	this.retries(0);
	before((done) => getCredentials(done));

	describe('[/ldap.syncNow]', () => {
		it('should require a second factor for LDAP synchronization', async function () {
			await request
				.post(api('ldap.syncNow'))
				.set(credentials)
				.expect('Content-Type', 'application/json')
				.expect(400)
				.expect((res: Response) => {
					expect(res.body).to.have.property('success', false);
					expect(res.body).to.have.property('errorType', 'totp-required');
				});
		});


	});

	describe('[/ldap.testSearch]', () => {
		before(async () => {
			return updatePermission('test-admin-options', ['admin']);
		});

		after(async () => {
			return updatePermission('test-admin-options', ['admin']);
		});

		it('should not allow testing LDAP search if user does NOT have the test-admin-options permission', async () => {
			await updatePermission('test-admin-options', []);
			await request
				.post(api('ldap.testSearch'))
				.set(credentials)
				.send({
					username: 'test-search',
				})
				.expect('Content-Type', 'application/json')
				.expect(403)
				.expect((res: Response) => {
					expect(res.body).to.have.property('success', false);
					expect(res.body).to.have.property('error', 'User does not have the permissions required for this action [error-unauthorized]');
				});
		});
	});

	describe('[/ldap.testConnection]', () => {
		before(async () => {
			return updatePermission('test-admin-options', ['admin']);
		});

		after(async () => {
			return updatePermission('test-admin-options', ['admin']);
		});

		it('should not allow testing LDAP connection if user does NOT have the test-admin-options permission', async () => {
			await updatePermission('test-admin-options', []);
			await request
				.post(api('ldap.testConnection'))
				.set(credentials)
				.expect('Content-Type', 'application/json')
				.expect(403)
				.expect((res: Response) => {
					expect(res.body).to.have.property('success', false);
					expect(res.body).to.have.property('error', 'User does not have the permissions required for this action [error-unauthorized]');
				});
		});
	});
});
