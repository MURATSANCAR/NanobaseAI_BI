const blockedDomains = ['rocket.chat', 'rocketchat.github.io', 'rocketchat.atlassian.net'];

/** Reject vendor destinations before DNS, including destinations reached through redirects. */
export function assertNonVendorDestination(input: string): void {
	const url = new URL(input);
	const hostname = url.hostname.toLowerCase().replace(/\.+$/, '');
	if (blockedDomains.some((domain) => hostname === domain || hostname.endsWith(`.${domain}`))) {
		throw new Error('error-vendor-destination-blocked');
	}

	// GitHub hosts other organizations too; block only the vendor's namespace.
	const githubHosts = ['github.com', 'www.github.com', 'raw.githubusercontent.com', 'codeload.github.com'];
	if (!githubHosts.includes(hostname) && hostname !== 'api.github.com') {
		return;
	}

	let pathname: string;
	try {
		pathname = decodeURIComponent(url.pathname).toLowerCase();
	} catch {
		throw new Error('error-invalid-destination-path');
	}
	const vendorPath = githubHosts.includes(hostname)
		? /^\/rocketchat(?:\/|$)/.test(pathname)
		: /^\/(?:repos|orgs|users)\/rocketchat(?:\/|$)/.test(pathname);
	if (vendorPath) {
		throw new Error('error-vendor-destination-blocked');
	}
}
