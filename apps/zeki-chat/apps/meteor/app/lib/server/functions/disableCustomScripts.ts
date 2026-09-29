import { Capabilities } from '@zeki.chat/capabilities';

export const disableCustomScripts = () => {
	const license = Capabilities.getLicense();

	if (!license) {
		return false;
	}

	const isCustomScriptDisabled = process.env.DISABLE_CUSTOM_SCRIPTS === 'true';
	const isTrialLicense = license?.information.trial;

	return isCustomScriptDisabled && isTrialLicense;
};
