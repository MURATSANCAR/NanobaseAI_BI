import { makeFunction } from '@zeki.chat/patch-injection';
import type { BrokerNode } from 'moleculer';

export const getInstanceList = makeFunction(async (): Promise<BrokerNode[]> => []);
