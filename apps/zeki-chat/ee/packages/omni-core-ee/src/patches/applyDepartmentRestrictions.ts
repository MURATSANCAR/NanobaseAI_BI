import type { ILivechatDepartment } from '@rocket.chat/core-typings';
import { Capabilities } from '@zeki.chat/capabilities';
import { applyDepartmentRestrictions } from '@rocket.chat/omni-core';
import type { FilterOperators } from 'mongodb';

import { addQueryRestrictionsToDepartmentsModel } from '../units/addRoleBasedRestrictionsToDepartment';
import { hooksLogger } from '../utils/logger';

export const applyDepartmentRestrictionsPatch = () => {
	applyDepartmentRestrictions.patch(
		async (
			prev: (query: FilterOperators<ILivechatDepartment>, userId: string) => FilterOperators<ILivechatDepartment>,
			query: FilterOperators<ILivechatDepartment> = {},
			userId: string,
		) => {
			if (!Capabilities.hasModule('livechat-enterprise')) {
				return prev(query, userId);
			}

			hooksLogger.debug('Applying department query restrictions');
			return addQueryRestrictionsToDepartmentsModel(query, userId);
		},
	);
};
