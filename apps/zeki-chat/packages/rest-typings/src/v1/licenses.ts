import type { LicenseInfo } from '@rocket.chat/core-typings';

import { ajvQuery } from './Ajv';

type licensesInfoProps = {
	loadValues?: boolean;
};

const licensesInfoPropsSchema = {
	type: 'object',
	properties: {
		loadValues: {
			type: 'boolean',
		},
	},
	required: [],
	additionalProperties: false,
};

export const isLicensesInfoProps = ajvQuery.compile<licensesInfoProps>(licensesInfoPropsSchema);

export type LicensesEndpoints = {
	'/v1/licenses.info': {
		GET: (params: licensesInfoProps) => {
			license: LicenseInfo;
		};
	};
	'/v1/licenses.maxActiveUsers': {
		GET: () => { maxActiveUsers: number | null; activeUsers: number };
	};
};
