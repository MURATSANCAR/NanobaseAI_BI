const vendorDomains = ['rocket.chat', 'rocketchat.github.io', 'rocketchat.atlassian.net'];

export const isVendorUrl = (input: string): boolean => {
	try {
		const url = new URL(input, window.location.href);
		const hostname = url.hostname.toLowerCase().replace(/\.+$/, '');
		if (vendorDomains.some((domain) => hostname === domain || hostname.endsWith(`.${domain}`))) {
			return true;
		}
		const pathname = decodeURIComponent(url.pathname).toLowerCase();
		if (['github.com', 'www.github.com', 'raw.githubusercontent.com', 'codeload.github.com'].includes(hostname)) {
			return /^\/rocketchat(?:\/|$)/.test(pathname);
		}
		return hostname === 'api.github.com' && /^\/(?:repos|orgs|users)\/rocketchat(?:\/|$)/.test(pathname);
	} catch {
		return true;
	}
};
