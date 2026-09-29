export type CapabilitiesEndpoints = {
	'/v1/capabilities.info': {
		GET: () => { capabilities: { modules: string[] } };
	};
};
