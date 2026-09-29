import { TrashRaw } from '@zeki.chat/models';

import { db } from './utils';

const Trash = new TrashRaw(db);
export const trashCollection = Trash.col;
