import type { IRole } from '@zeki.chat/core-typings';

export interface ITeamMemberParams {
	userId: string;
	roles?: Array<IRole['_id']> | null;
}
