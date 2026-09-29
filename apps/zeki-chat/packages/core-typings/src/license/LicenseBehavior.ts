import type { LicenseLimitKind } from './ILicenseV3';
import type { CapabilityModule } from './CapabilityModule';

export type LicenseBehavior =
	| 'invalidate_license'
	| 'start_fair_policy'
	| 'prevent_action'
	| 'allow_action'
	| 'prevent_installation'
	| 'disable_modules';

export type BehaviorWithContext =
	| {
			behavior: LicenseBehavior;
			modules?: CapabilityModule[];
			reason: 'limit';
			limit?: LicenseLimitKind;
	  }
	| {
			behavior: LicenseBehavior;
			modules?: CapabilityModule[];
			reason: 'period' | 'url';
	  };
