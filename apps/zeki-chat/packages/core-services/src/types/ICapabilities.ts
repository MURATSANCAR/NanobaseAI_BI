import type { IServiceClass } from './ServiceClass';

export interface ICapabilities extends IServiceClass {
	hasModule(feature: string): boolean;

	isReady(): boolean;

	getModules(): string[];

	getGuestPermissions(): string[];
}
