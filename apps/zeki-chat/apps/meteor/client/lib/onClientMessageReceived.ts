import type { IMessage } from '@zeki.chat/core-typings';

import { createAsyncTransformChain } from '../../lib/transforms';

export const onClientMessageReceived = createAsyncTransformChain<IMessage>();
