import { escapeRegExp } from '@rocket.chat/string-helpers';
import { isAbsoluteURL } from '@rocket.chat/tools';

import { ltrim, rtrim, trim } from '../../../lib/utils/stringUtils';

// Zeki: go.rocket.chat deep links were removed; every generated URL points to this workspace only.
export const _getURL = (
	path: string,
	// eslint-disable-next-line @typescript-eslint/naming-convention
	{ cdn, full, cloud, _cdn_prefix, _root_url_path_prefix, _site_url }: Record<string, any>,
	_deeplinkUrl?: string,
): string => {
	if (isAbsoluteURL(path)) {
		return path;
	}

	const [_path, _query] = path.split('?');
	path = _path;
	const query = _query ? `?${_query}` : '';

	const siteUrl = rtrim(trim(_site_url || ''), '/');
	const cdnPrefix = rtrim(trim(_cdn_prefix || ''), '/');
	const pathPrefix = rtrim(trim(_root_url_path_prefix || ''), '/');

	const finalPath = ltrim(trim(path), '/');

	const url = rtrim(`${pathPrefix}/${finalPath}`, '/') + query;

	// Zeki: `cloud` used to build a go.rocket.chat deep link; it now yields the local absolute URL.
	if (cloud) {
		return siteUrl.replace(new RegExp(`${escapeRegExp(pathPrefix)}$`), '') + url;
	}

	if (cdn && cdnPrefix !== '') {
		return cdnPrefix + url;
	}

	if (full) {
		return siteUrl.replace(new RegExp(`${escapeRegExp(pathPrefix)}$`), '') + url;
	}

	return url;
};

export const getURLWithoutSettings = (
	path: string,
	// eslint-disable-next-line @typescript-eslint/naming-convention
	{
		cdn = true,
		full = false,
		cloud = false,
		cloud_route = '',
		cloud_params = {},
	}: {
		cdn?: boolean;
		full?: boolean;
		cloud?: boolean;
		cloud_route?: string;
		cloud_params?: Record<string, string>;
	},
	cdnPrefix: string,
	siteUrl: string,
	cloudDeepLinkUrl?: string,
): string =>
	_getURL(
		path,
		{
			cdn,
			full,
			cloud,
			cloud_route,
			cloud_params,
			_cdn_prefix: cdnPrefix,
			_root_url_path_prefix: __meteor_runtime_config__.ROOT_URL_PATH_PREFIX,
			_site_url: siteUrl,
		},
		cloudDeepLinkUrl,
	);
