import type { ILivechatDepartment } from '@zeki.chat/core-typings';
import { LivechatRooms, LivechatDepartment } from '@zeki.chat/models';

import { onNewRoom } from '../../../../../app/livechat/server/lib/hooks';

onNewRoom.patch(async (originalFn, room) => {
	await originalFn(room);
	if (!room.departmentId) {
		return;
	}

	const department = await LivechatDepartment.findOneById<Pick<ILivechatDepartment, '_id' | 'ancestors'>>(room.departmentId, {
		projection: { ancestors: 1 },
	});

	if (!department?.ancestors) {
		return;
	}

	const { ancestors } = department;
	await LivechatRooms.updateDepartmentAncestorsById(room._id, ancestors);
});
