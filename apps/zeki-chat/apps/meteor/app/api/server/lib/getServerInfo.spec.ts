import { expect } from 'chai';
import { describe, it, before } from 'mocha';
import proxyquire from 'proxyquire';
import sinon from 'sinon';

const hasAllPermissionAsyncMock = sinon.stub();

// #ToDo: Fix those tests in a separate PR
describe.skip('#getServerInfo()', () => {
	let getServerInfo: any;

	before(() => {
		const { getServerInfo: importedGetServerInfo } = proxyquire.noCallThru().load('./getServerInfo', {
			'../../../utils/rocketchat.info': {
				Info: {
					version: '3.0.1',
				},
			},
			'../../../authorization/server/functions/hasPermission': {
				hasPermissionAsync: hasAllPermissionAsyncMock,
			},
		});

		getServerInfo = importedGetServerInfo;
	});

	beforeEach(() => {
		hasAllPermissionAsyncMock.reset();
	});

	it('should return only the version (without the patch info) when the user is not present', async () => {
		expect(await getServerInfo(undefined)).to.be.eql({ version: '3.0' });
	});

	it('should return only the version (without the patch info) when the user present but they dont have permission', async () => {
		hasAllPermissionAsyncMock.resolves(false);
		expect(await getServerInfo('userId')).to.be.eql({ version: '3.0' });
	});
});
