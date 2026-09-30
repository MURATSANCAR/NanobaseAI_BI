import type { IRole } from '@zeki.chat/core-typings';
import { Roles } from '@zeki.chat/models';

export const getRoles = async (): Promise<IRole[]> => Roles.find().toArray();

export const getRoleIds = async (): Promise<IRole['_id'][]> =>
	(await Roles.find({}, { projection: { _id: 1 } }).toArray()).map(({ _id }) => _id);
