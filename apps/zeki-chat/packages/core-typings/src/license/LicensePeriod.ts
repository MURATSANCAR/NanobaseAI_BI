import type { LicenseBehavior } from './LicenseBehavior';
import type { CapabilityModule } from './CapabilityModule';

export type LicensePeriod = {
	validFrom?: string;
	validUntil?: string;
	invalidBehavior: LicenseBehavior;
} & ({ validFrom: string } | { validUntil: string }) &
	({ invalidBehavior: 'disable_modules'; modules: CapabilityModule[] } | { invalidBehavior: Exclude<LicenseBehavior, 'disable_modules'> });
