import { LivechatDepartment } from '@zeki.chat/models';
import { makeFunction } from '@zeki.chat/patch-injection';

export const isDepartmentCreationAvailable = makeFunction(async (): Promise<boolean> => {
	// Only one department can exist at a time
	return (await LivechatDepartment.countTotal()) === 0;
});
