import { useEffect } from 'react';

import { isVendorUrl } from '../../../lib/utils/isVendorUrl';

// Protect ordinary link activation across message HTML and shared link components.
// Browser context-menu navigation and manually entered URLs remain user-controlled.
export const useVendorLinkGuard = () => {
	useEffect(() => {
		const onActivate = (event: MouseEvent) => {
			const anchor = event.composedPath().find((node): node is HTMLAnchorElement => node instanceof HTMLAnchorElement);
			if (!anchor || !isVendorUrl(anchor.href)) {
				return;
			}
			event.preventDefault();
			event.stopImmediatePropagation();
		};
		document.addEventListener('click', onActivate, true);
		document.addEventListener('auxclick', onActivate, true);
		return () => {
			document.removeEventListener('click', onActivate, true);
			document.removeEventListener('auxclick', onActivate, true);
		};
	}, []);
};
