import { registerModel } from '@zeki.chat/models';

import { ReadReceiptsArchiveRaw } from './raw/ReadReceiptsArchive';
import { db } from '../../../server/database/utils';

registerModel('IReadReceiptsArchiveModel', new ReadReceiptsArchiveRaw(db));
