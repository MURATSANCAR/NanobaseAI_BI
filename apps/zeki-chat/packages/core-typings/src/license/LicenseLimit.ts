import type { LicenseBehavior } from './LicenseBehavior';
import type { CapabilityModule } from './CapabilityModule';

export type LicenseLimit<T extends LicenseBehavior = LicenseBehavior> = {
	max: number;
	behavior: T;
} & (T extends 'disable_modules' ? { behavior: T; modules: CapabilityModule[] } : { behavior: T });
