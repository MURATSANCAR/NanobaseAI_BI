import type {
	ILicenseTag,
	LicenseEvents,
	ILicenseV2,
	ILicenseV3,
	LicenseLimitKind,
	LicenseBehavior,
	LicenseInfo,
	LimitContext,
	LicenseModule,
} from '@rocket.chat/core-typings';
import { Emitter } from '@rocket.chat/emitter';

import { getLicenseLimit } from './deprecated';
import type { getAppsConfig, getMaxActiveUsers, getUnmodifiedLicenseAndModules } from './deprecated';
import type { onLicense } from './events/deprecated';
import { licenseValidated } from './events/emitter';
import type {
	onBehaviorTriggered,
	onInvalidFeature,
	onInvalidateLicense,
	onLimitReached,
	onModule,
	onToggledFeature,
	onValidFeature,
	onValidateLicense,
} from './events/listeners';
import type { overwriteClassOnLicense } from './events/overwriteClassOnLicense';
import { buildInternalLicense } from './internalLicense';
import type { getModuleDefinition, hasModule } from './modules';
import { getExternalModules, getModules, replaceModules } from './modules';
import type { getTags } from './tags';
import { replaceTags } from './tags';
import type { setLicenseLimitCounter } from './validation/getCurrentValueForLicenseLimit';
import { getCurrentValueForLicenseLimit } from './validation/getCurrentValueForLicenseLimit';

const globalLimitKinds: LicenseLimitKind[] = ['activeUsers', 'guestUsers', 'privateApps', 'marketplaceApps', 'monthlyActiveContacts'];

const preventableLimitKinds: LicenseLimitKind[] = [
	'activeUsers',
	'guestUsers',
	'roomsPerGuest',
	'privateApps',
	'marketplaceApps',
	'monthlyActiveContacts',
];

// Zeki: the only license is the in-memory internal one. Loading, decrypting, validating, syncing, removing and
// invalidating licenses were deleted — there is no code path that accepts a license from outside.
export abstract class LicenseManager extends Emitter<LicenseEvents> {
	abstract hasModule: typeof hasModule;

	abstract getModules: typeof getModules;

	abstract getModuleDefinition: typeof getModuleDefinition;

	abstract getExternalModules: typeof getExternalModules;

	abstract getTags: typeof getTags;

	abstract overwriteClassOnLicense: typeof overwriteClassOnLicense;

	abstract setLicenseLimitCounter: typeof setLicenseLimitCounter;

	abstract getCurrentValueForLicenseLimit: typeof getCurrentValueForLicenseLimit;

	abstract isLimitReached<T extends LicenseLimitKind>(action: T, context?: Partial<LimitContext<T>>): Promise<boolean>;

	abstract onValidFeature: typeof onValidFeature;

	abstract onInvalidFeature: typeof onInvalidFeature;

	abstract onToggledFeature: typeof onToggledFeature;

	abstract onModule: typeof onModule;

	abstract onValidateLicense: typeof onValidateLicense;

	abstract onInvalidateLicense: typeof onInvalidateLicense;

	abstract onLimitReached: typeof onLimitReached;

	abstract onBehaviorTriggered: typeof onBehaviorTriggered;

	// Deprecated:
	abstract onLicense: typeof onLicense;

	// Deprecated:
	abstract getMaxActiveUsers: typeof getMaxActiveUsers;

	// Deprecated:
	abstract getAppsConfig: typeof getAppsConfig;

	// Deprecated:
	abstract getUnmodifiedLicenseAndModules: typeof getUnmodifiedLicenseAndModules;

	dataCounters = new Map<LicenseLimitKind, (context?: LimitContext<LicenseLimitKind>) => Promise<number>>();

	tags = new Set<ILicenseTag>();

	modules = new Set<LicenseModule>();

	protected _license: ILicenseV3 | undefined;

	private _unmodifiedLicense: ILicenseV2 | ILicenseV3 | undefined;

	private _valid: boolean | undefined;

	private states = new Map<LicenseBehavior, Map<LicenseLimitKind, boolean>>();

	public get shouldPreventActionResults() {
		const state = this.states.get('prevent_action') ?? new Map<LicenseLimitKind, boolean>();

		this.states.set('prevent_action', state);

		return state;
	}

	public get license(): ILicenseV3 | undefined {
		return this._license;
	}

	public get unmodifiedLicense(): ILicenseV2 | ILicenseV3 | undefined {
		return this._unmodifiedLicense;
	}

	public get valid(): boolean | undefined {
		return this._valid;
	}

	// Zeki: called once from the server license startup, after settings are ready (same timing as a stored license).
	public applyInternalLicense(): void {
		if (this._valid) {
			return;
		}

		const license = buildInternalLicense();

		this._license = license;
		this._unmodifiedLicense = license;
		this._valid = true;
		this.states.clear();

		replaceTags.call(this, license.information.tags || []);
		replaceModules.call(
			this,
			license.grantedModules.map(({ module }) => module),
		);

		licenseValidated.call(this);
	}

	public hasValidLicense(): boolean {
		return Boolean(this.getLicense());
	}

	public getLicense(): ILicenseV3 | undefined {
		if (this._valid && this._license) {
			return this._license;
		}

		return undefined;
	}

	public syncShouldPreventActionResults(actions: Record<LicenseLimitKind, boolean>): void {
		for (const [action, shouldPreventAction] of Object.entries(actions)) {
			this.shouldPreventActionResults.set(action as LicenseLimitKind, shouldPreventAction);
		}
	}

	public async shouldPreventActionResultsMap(): Promise<{
		[key in LicenseLimitKind]: boolean;
	}> {
		return Object.fromEntries(preventableLimitKinds.map((limit) => [limit, false])) as { [key in LicenseLimitKind]: boolean };
	}

	public async shouldPreventAction<T extends LicenseLimitKind>(
		_action: T,
		_extraCount = 0,
		_context: Partial<LimitContext<T>> = {},
		_options: { suppressLog?: boolean } = {},
	): Promise<boolean> {
		return false;
	}

	public async getInfo({
		limits: includeLimits,
		currentValues: loadCurrentValues,
		license: includeLicense,
	}: {
		limits: boolean;
		currentValues: boolean;
		license: boolean;
	}): Promise<LicenseInfo> {
		const activeModules = getModules.call(this);
		const externalModules = getExternalModules.call(this);
		const license = this.getLicense();

		// Get all limits present in the license and their current value
		const limits = Object.fromEntries(
			(includeLimits &&
				(await Promise.all(
					globalLimitKinds
						.map((limitKey) => [limitKey, getLicenseLimit(license, limitKey)] as const)
						.map(async ([limitKey, max]) => {
							return [
								limitKey,
								{
									...(loadCurrentValues && { value: await getCurrentValueForLicenseLimit.call(this, limitKey) }),
									max,
								},
							];
						}),
				))) ||
				[],
		);

		return {
			license: (includeLicense && license) || undefined,
			activeModules,
			externalModules,
			preventedActions: await this.shouldPreventActionResultsMap(),
			limits: limits as Record<LicenseLimitKind, { max: number; value: number }>,
			tags: license?.information.tags || [],
			trial: Boolean(license?.information.trial),
			hasValidLicense: this.hasValidLicense(),
		};
	}
}
