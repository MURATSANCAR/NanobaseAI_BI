import type { CapabilityRegistry } from '@zeki.chat/capabilities';
import type { MiddlewareHandler } from 'hono';
import type { TypedOptions } from '../../../../../app/api/server/definition';

export const capabilities = (options: TypedOptions, registry: CapabilityRegistry): MiddlewareHandler => async (c, next) => {
	if (options.capabilities?.some((module) => !registry.hasModule(module))) {
		return c.json({ success: false, error: 'Capability unavailable', errorType: 'error-action-not-allowed' }, 400);
	}
	return next();
};
