import { AppInstallationSource, type IAppStorageItem } from '@zeki.chat/apps/dist/server/storage/IAppStorageItem';
import { AppStatus } from '@zeki.chat/apps-engine/definition/AppStatus';
import type { Apps } from '@zeki.chat/core-services';
import type { CapabilityRegistry } from '@zeki.chat/capabilities';
import { expect } from 'chai';

import { _canEnableApp } from '../../../../../ee/app/capabilities/server/canEnableApp';

const getDefaultApp = (): IAppStorageItem => ({
	_id: '6706d9258e0ca97c2f0cc885',
	id: '2e14ff6e-b4d5-4c4c-b12b-b1b1d15ec630',
	info: {
		id: '2e14ff6e-b4d5-4c4c-b12b-b1b1d15ec630',
		version: '0.0.1',
		requiredApiVersion: '^1.19.0',
		iconFile: 'icon.png',
		author: { name: 'a', homepage: 'a', support: 'a' },
		name: 'Add-on test',
		nameSlug: 'add-on-test',
		classFile: 'AddOnTestApp.js',
		description: 'a',
		implements: [],
		iconFileContent: '',
	},
	status: AppStatus.UNKNOWN,
	settings: {},
	implemented: {},
	installationSource: AppInstallationSource.PRIVATE,
	languageContent: {},
	sourcePath: 'GridFS:/6706d9258e0ca97c2f0cc880',
	signature: '',
	createdAt: new Date('2024-10-09T19:27:33.923Z'),
	updatedAt: new Date('2024-10-09T19:27:33.923Z'),
});

describe('canEnableApp', () => {
	const registry = { hasModule: (module: string) => module === 'custom-roles' } as CapabilityRegistry;
	const initialized = { isInitialized: async () => true } as unknown as typeof Apps;
	const deps = { Apps: initialized, Capabilities: registry };

	it('requires an initialized application engine', () => {
		return expect(_canEnableApp({ ...deps, Apps: { isInitialized: async () => false } as unknown as typeof Apps }, getDefaultApp()))
			.to.eventually.be.rejectedWith('apps-engine-not-initialized');
	});
	it('allows a private application without workspace quotas', () => {
		return expect(_canEnableApp(deps, getDefaultApp())).to.not.eventually.be.rejected;
	});
	it('requires the implementation used by a private add-on', () => {
		const app = getDefaultApp();
		app.info.addon = 'unknown.external-addon';
		return expect(_canEnableApp(deps, app)).to.eventually.be.rejectedWith('app-addon-not-available');
	});
	it('allows a private add-on backed by a local implementation', () => {
		const app = getDefaultApp();
		app.info.addon = 'custom-roles';
		return expect(_canEnableApp(deps, app)).to.not.eventually.be.rejected;
	});
	it('does not authorize marketplace applications through local capabilities', () => {
		const app = getDefaultApp();
		app.installationSource = AppInstallationSource.MARKETPLACE;
		return expect(_canEnableApp(deps, app)).to.eventually.be.rejectedWith('marketplace-unavailable');
	});
	it('does not bypass the marketplace boundary for migrated applications', () => {
		const app = getDefaultApp();
		app.installationSource = AppInstallationSource.MARKETPLACE;
		app.migrated = true;
		return expect(_canEnableApp(deps, app)).to.eventually.be.rejectedWith('marketplace-unavailable');
	});
});
