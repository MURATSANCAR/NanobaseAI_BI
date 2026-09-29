import { startCapabilities } from './ee/app/capabilities/server/startup';
import { registerEEBroker } from './ee/server';
import { startFederationService as startFederationMatrixService } from './ee/server/startup/federation';

const registerLocalServices = async () => {
	await registerEEBroker();
};

const startFederation = async () => {
	await startFederationMatrixService();
};

export const startZekiChat = async () => {
	await registerLocalServices();

	await startCapabilities();

	await startFederation();
};
