import type { IRole } from '@zeki.chat/core-typings';

import { Roles } from '../../../../stores';

export const useRole = (_id?: IRole['_id']) => Roles.use((state) => (_id ? state.get(_id) : undefined));
