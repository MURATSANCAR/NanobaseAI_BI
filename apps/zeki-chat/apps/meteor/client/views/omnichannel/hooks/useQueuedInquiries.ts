import type { Inquiries } from '@zeki.chat/core-typings';

import { useOmnichannel } from './useOmnichannel';

export const useQueuedInquiries = (): Inquiries => useOmnichannel().inquiries;
