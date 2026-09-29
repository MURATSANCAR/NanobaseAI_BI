import type { LicenseLimitKind } from './ILicenseV3';
import type { BehaviorWithContext, LicenseBehavior } from './LicenseBehavior';
import type { CapabilityModule } from './CapabilityModule';

type ModuleValidation = Record<`${'invalid' | 'valid'}:${CapabilityModule}`, undefined>;
type BehaviorTriggered = Record<`behavior:${LicenseBehavior}`, { reason: BehaviorWithContext['reason']; limit?: LicenseLimitKind }>;
type BehaviorTriggeredToggled = Record<
	`behaviorToggled:${LicenseBehavior}`,
	{ reason: BehaviorWithContext['reason']; limit?: LicenseLimitKind }
>;

type LimitReached = Record<`limitReached:${LicenseLimitKind}`, undefined>;

export type LicenseEvents = ModuleValidation &
	BehaviorTriggeredToggled &
	BehaviorTriggered &
	LimitReached & {
		installed: undefined;
		removed: undefined;
		validate: undefined;
		invalidate: undefined;
		module: { module: CapabilityModule; external: boolean; valid: boolean };
		sync: undefined;
	};
