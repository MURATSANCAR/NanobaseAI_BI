import { Router } from '@rocket.chat/http-router';
import { ajv } from '@rocket.chat/rest-typings/dist/v1/Ajv';

const GetVersionsResponseSchema = {
	type: 'object',
	properties: {
		server: {
			type: 'object',
			properties: {
				name: {
					type: 'string',
					description: 'Server software name',
				},
				version: {
					type: 'string',
					description: 'Server software version',
				},
			},
			required: ['name', 'version'],
		},
	},
	required: ['server'],
};

const isGetVersionsResponseProps = ajv.compile(GetVersionsResponseSchema);

export const getFederationVersionsRoutes = (version: string) => {
	return new Router('/federation').get(
		'/v1/version',
		{
			response: {
				200: isGetVersionsResponseProps,
			},
			tags: ['Federation'],
			license: ['federation'],
		},
		async () => {
			const response = {
				// Zeki: server name advertised to federated peers.
				server: {
					name: 'Zeki AI',
					version,
				},
			};

			return {
				body: response,
				statusCode: 200,
			};
		},
	);
};
