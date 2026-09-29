import { Box, Throbber } from '@rocket.chat/fuselage';
import { useSession, useSetting } from '@rocket.chat/ui-contexts';
import type { LoginRoutes } from '@rocket.chat/web-ui-registration';
import RegistrationRoute from '@rocket.chat/web-ui-registration';
import { Meteor } from 'meteor/meteor';
import type { ReactElement, ReactNode } from 'react';
import { useEffect, useRef } from 'react';

import LoggedOutBanner from '../../../components/deviceManagement/LoggedOutBanner';
import { useIframe } from '../hooks/useIframe';

const LoginPage = ({ defaultRoute, children }: { defaultRoute?: LoginRoutes; children?: ReactNode }): ReactElement => {
	const localOnly = useSetting('Zeki_Local_Only', true);
	const showForcedLogoutBanner = useSession('forceLogout') as boolean | undefined;
	// useIframe asks the portal for a login token once on mount; it must not be asked twice,
	// because a second token login cancels the first one and reports an error.
	const { iframeLoginUrl, tryLogin, enabled: iframeEnabled } = useIframe();
	const attempted = useRef(false);

	useEffect(() => {
		if (!iframeEnabled || attempted.current) {
			return;
		}
		attempted.current = true;
		tryLogin();
	}, [iframeEnabled, tryLogin]);

	// Zeki: sign-in belongs to the portal. Only when the portal has no session for this browser
	// does the whole tab go to the portal login page; while the portal is asked, only a spinner shows.
	useEffect(() => {
		if (!iframeLoginUrl) {
			return;
		}
		if (localOnly) {
			try {
				const destination = new URL(iframeLoginUrl, window.location.href);
				if (destination.origin !== window.location.origin || destination.username || destination.password) {
					console.error('External login redirects are disabled');
					return;
				}
			} catch {
				return;
			}
		}
		const timer = setTimeout(() => {
			if (!Meteor.userId() && !Meteor.loggingIn()) {
				window.location.replace(iframeLoginUrl);
			}
		}, 1500);
		return () => clearTimeout(timer);
	}, [iframeLoginUrl, localOnly]);

	if (iframeEnabled) {
		return (
			<Box display='flex' alignItems='center' justifyContent='center' height='100vh'>
				<Throbber />
			</Box>
		);
	}

	return (
		<>
			{showForcedLogoutBanner && <LoggedOutBanner />}
			<RegistrationRoute defaultRoute={defaultRoute}>{children}</RegistrationRoute>
		</>
	);
};

export default LoginPage;
