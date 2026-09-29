import type { ILivechatDepartmentAgents } from '@zeki.chat/core-typings';
import { LivechatDepartmentAgents } from '@zeki.chat/models';

export async function findAgentDepartments({
	enabledDepartmentsOnly,
	agentId,
}: {
	enabledDepartmentsOnly?: boolean;
	agentId: string;
}): Promise<{ departments: (ILivechatDepartmentAgents & { departmentName: string })[] }> {
	return {
		departments: await LivechatDepartmentAgents.findDepartmentsOfAgent(agentId, enabledDepartmentsOnly).toArray(),
	};
}
