import type { CloudRegistrationStatus } from '@rocket.chat/core-typings';
import { ajv, validateUnauthorizedErrorResponse, validateForbiddenErrorResponse, validateBadRequestErrorResponse } from '@rocket.chat/rest-typings';

import { retrieveRegistrationStatus } from '../../../cloud/server/functions/retrieveRegistrationStatus';
import { API } from '../api';

/**
 * Zeki: Rocket.Chat Cloud is permanently disconnected.
 * Registration (manual, intent, pre-intent, confirmation poll) endpoints were removed.
 * The remaining endpoints never contact any Rocket.Chat service.
 */

const successResponseSchema = ajv.compile<void>({
	type: 'object',
	properties: { success: { type: 'boolean', enum: [true] } },
	required: ['success'],
	additionalProperties: false,
});

const registrationStatusResponseSchema = ajv.compile<{ registrationStatus: CloudRegistrationStatus }>({
	type: 'object',
	properties: {
		registrationStatus: { $ref: '#/components/schemas/CloudRegistrationStatus' },
		success: { type: 'boolean', enum: [true] },
	},
	required: ['registrationStatus', 'success'],
	additionalProperties: false,
});

API.v1.get(
	'cloud.registrationStatus',
	{
		authRequired: true,
		permissionsRequired: ['manage-cloud'],
		response: {
			200: registrationStatusResponseSchema,
			401: validateUnauthorizedErrorResponse,
			403: validateForbiddenErrorResponse,
		},
	},
	async function action() {
		const registrationStatus = await retrieveRegistrationStatus();

		return API.v1.success({ registrationStatus });
	},
);

API.v1.post(
	'cloud.syncWorkspace',
	{
		authRequired: true,
		permissionsRequired: ['manage-cloud'],
		rateLimiterOptions: { numRequestsAllowed: 2, intervalTimeInMS: 60000 },
		response: {
			200: successResponseSchema,
			400: validateBadRequestErrorResponse,
			401: validateUnauthorizedErrorResponse,
			403: validateForbiddenErrorResponse,
		},
	},
	async function action() {
		return API.v1.failure('Cloud sync is disabled');
	},
);

API.v1.post(
	'cloud.removeLicense',
	{
		authRequired: true,
		permissionsRequired: ['manage-cloud'],
		rateLimiterOptions: { numRequestsAllowed: 2, intervalTimeInMS: 60000 },
		response: {
			200: successResponseSchema,
			400: validateBadRequestErrorResponse,
			401: validateUnauthorizedErrorResponse,
			403: validateForbiddenErrorResponse,
		},
	},
	async function action() {
		return API.v1.failure('Cloud license removal is disabled');
	},
);
