import type { ILicenseV3 } from '@rocket.chat/core-typings';
import { CoreModules } from '@rocket.chat/core-typings';

// Zeki: in-memory license for the test environment — every core module, no limits, no statistics report requirement.
export const buildInternalLicense = (): ILicenseV3 => ({
	version: '3.0',
	information: {
		autoRenew: true,
		trial: false,
		offline: true,
		createdAt: new Date(0).toISOString(),
		grantedBy: { method: 'manual' },
		grantedTo: { name: 'Zeki AI', company: 'Zeki AI' },
		tags: [{ name: 'Zeki AI', color: '#7C5CFF' }],
	},
	validation: {
		serverUrls: [{ value: '.*', type: 'regex' }],
		validPeriods: [{ validUntil: '2099-12-31T23:59:59.000Z', invalidBehavior: 'invalidate_license' }],
		legalTextAgreement: { type: 'not-required' },
		statisticsReport: { required: false },
	},
	grantedModules: CoreModules.map((module) => ({ module })),
	limits: {},
});
