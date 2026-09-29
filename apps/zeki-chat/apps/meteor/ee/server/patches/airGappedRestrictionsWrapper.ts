import { applyAirGappedRestrictionsValidation } from '../../../app/license/server/airGappedRestrictionsWrapper';

// Zeki: air-gapped restriction removed; the wrapper is a pass-through.
applyAirGappedRestrictionsValidation.patch(async <T>(_: any, fn: () => Promise<T>): Promise<T> => {
	return fn();
});
