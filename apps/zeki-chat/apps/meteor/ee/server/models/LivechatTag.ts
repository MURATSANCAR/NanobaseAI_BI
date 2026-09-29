import { registerModel } from '@zeki.chat/models';

import { LivechatTagRaw } from './raw/LivechatTag';
import { db } from '../../../server/database/utils';

registerModel('ILivechatTagModel', new LivechatTagRaw(db));
