import { useEffect } from 'react';

import { useIframe } from './useIframe';

export const useIframeLoginListener = () => {
	const { enabled: iframeEnabled, tryLogin, loginWithToken } = useIframe();
	// Zeki: the login page asks the portal once. Asking again here (and again whenever the stored token
	// changes) made each token login cancel the previous one in a loop until the rate limit locked the user out.

	useEffect(() => {
		if (!iframeEnabled) {
			return;
		}
		const messageListener = (e: MessageEvent) => {
			if (!(typeof e.data === 'function' || (typeof e.data === 'object' && !!e.data))) {
				return;
			}

			switch (e.data.event) {
				case 'try-iframe-login':
					tryLogin((error) => {
						if (error) {
							e.source?.postMessage(
								{
									event: 'login-error',
									response: error.message,
								},
								{ targetOrigin: e.origin },
							);
						}
					});
					break;

				case 'login-with-token':
					loginWithToken(e.data, (error) => {
						if (error) {
							e.source?.postMessage(
								{
									event: 'login-error',
									response: error.message,
								},
								{ targetOrigin: e.origin },
							);
						}
					});
					break;
			}
		};

		window.addEventListener('message', messageListener);
		return () => {
			window.removeEventListener('message', messageListener);
		};
	}, [iframeEnabled, loginWithToken, tryLogin]);
};
