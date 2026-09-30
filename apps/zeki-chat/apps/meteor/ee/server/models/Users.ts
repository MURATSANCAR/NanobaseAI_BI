import { registerModel } from '@zeki.chat/models';

import { UsersEE } from './raw/Users';
import { trashCollection } from '../../../server/database/trash';
import { db } from '../../../server/database/utils';

registerModel('IUsersModel', new UsersEE(db, trashCollection));
