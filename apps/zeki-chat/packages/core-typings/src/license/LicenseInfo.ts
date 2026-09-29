import type { ILicenseTag } from './ILicenseTag';
import type { ExternalModule, ILicenseV3, LicenseLimitKind } from './ILicenseV3';
import type { CapabilityModule } from './CapabilityModule';
import type { ICloudSyncAnnouncement } from '../cloud';

export type LicenseInfo = {
	license?: ILicenseV3;
	activeModules: CapabilityModule[];
	externalModules: ExternalModule[];
	preventedActions: Record<LicenseLimitKind, boolean>;
	limits: Record<LicenseLimitKind, { value?: number; max: number }>;
	tags: ILicenseTag[];
	trial: boolean;
	hasValidLicense: boolean;
	cloudSyncAnnouncement?: ICloudSyncAnnouncement;
};
