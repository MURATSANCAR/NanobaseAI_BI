/* eslint-disable react-hooks/rules-of-hooks */

import { API } from '../../../app/api/server/api';
import type { NonEnterpriseTwoFactorOptions, Options } from '../../../app/api/server/definition';
import { use } from '../../../app/settings/server/Middleware';

// Sensitive endpoints require a second factor independently of product capabilities.

const isNonEnterpriseTwoFactorOptions = (options?: Options): options is NonEnterpriseTwoFactorOptions =>
	!!options && 'forceTwoFactorAuthenticationForNonEnterprise' in options && Boolean(options.forceTwoFactorAuthenticationForNonEnterprise);

API.v1.processTwoFactor = use(API.v1.processTwoFactor, ([params, ...context], next) => {
	if (isNonEnterpriseTwoFactorOptions(params.options)) {
		const options: NonEnterpriseTwoFactorOptions = {
			...params.options,
			twoFactorOptions: {
				disableRememberMe: true,
				requireSecondFactor: true,
				disablePasswordFallback: false,
			},
			twoFactorRequired: true,
			authRequired: true,
		};

		return next(
			{
				...params,
				options,
			},
			...context,
		);
	}

	return next(params, ...context);
});
