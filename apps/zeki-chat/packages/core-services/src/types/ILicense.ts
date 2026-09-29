import type { IServiceClass } from './ServiceClass';

export interface ICapabilities extends IServiceClass {
	hasModule(feature: string): boolean;

	hasValidLicense(): boolean;

	getModules(): string[];

	getGuestPermissions(): string[];
}
