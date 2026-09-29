import { useVerifyPassword } from '@zeki.chat/ui-contexts';

export const useValidatePassword = (password: string): boolean => {
	const passwordVerifications = useVerifyPassword(password);
	return passwordVerifications.valid;
};
