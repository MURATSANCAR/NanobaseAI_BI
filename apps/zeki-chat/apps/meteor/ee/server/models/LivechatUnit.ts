import { registerModel } from '@zeki.chat/models';

import { LivechatUnitRaw } from './raw/LivechatUnit';
import { db } from '../../../server/database/utils';

// @ts-expect-error - Overriding base types :)
registerModel('ILivechatUnitModel', new LivechatUnitRaw(db));
