import { useCallback } from 'react';

import { InvalidUrlError } from '../lib/errors/InvalidUrlError';
import { isVendorUrl } from '../lib/utils/isVendorUrl';

export const useExternalLink = () => {
	return useCallback((url: string | undefined) => {
		if (!url || isVendorUrl(url)) {
			throw new InvalidUrlError();
		}
		window.open(url, '_blank', 'noopener noreferrer');
	}, []);
};
