import type { ILivechatDepartment } from '@zeki.chat/core-typings';
import { makeFunction } from '@zeki.chat/patch-injection';
import type { FilterOperators } from 'mongodb';

export const applyDepartmentRestrictions = makeFunction(async (query: FilterOperators<ILivechatDepartment> = {}, _userId: string) => {
	return query;
});
