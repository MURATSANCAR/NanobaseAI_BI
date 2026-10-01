import type { OmichannelRoutingConfig } from '@zeki.chat/core-typings';

import { useOmnichannel } from './useOmnichannel';

export const useOmnichannelRouteConfig = (): OmichannelRoutingConfig | undefined => useOmnichannel().routeConfig;
