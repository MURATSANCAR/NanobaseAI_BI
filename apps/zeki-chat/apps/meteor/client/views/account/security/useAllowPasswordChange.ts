import { useSetting, useUser } from '@zeki.chat/ui-contexts';

export const useAllowPasswordChange = () => {
	const user = useUser();

	let allowPasswordChange = useSetting('Accounts_AllowPasswordChange');
	const allowOAuthPasswordChange = useSetting('Accounts_AllowPasswordChangeForOAuthUsers');

	const hasLocalPassword = Boolean(user?.services?.password?.exists);

	if (allowPasswordChange && !allowOAuthPasswordChange) {
		allowPasswordChange = hasLocalPassword;
	}

	return { allowPasswordChange, hasLocalPassword };
};
