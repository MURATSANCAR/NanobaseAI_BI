import { Capabilities } from '@rocket.chat/core-services';
import { createMiddleware } from 'hono/factory';

export const isLicenseEnabledMiddleware = createMiddleware(async (c, next) => {
	if (!(await Capabilities.hasModule('federation'))) {
		return c.json({ error: 'Federation is not enabled' }, 403);
	}
	return next();
});
