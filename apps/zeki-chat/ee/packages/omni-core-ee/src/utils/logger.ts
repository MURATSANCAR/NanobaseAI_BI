import { Logger } from '@zeki.chat/logger';

export const defaultLogger = new Logger('OmniCore-ee');
export const hooksLogger = defaultLogger.section('hooks');
