import { startTracing } from '@zeki.chat/tracing';

import { client } from './database/utils';

startTracing({ service: 'core', db: client });
