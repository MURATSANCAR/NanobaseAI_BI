import type { IAppServerOrchestrator, IAppsRole } from '@zeki.chat/apps';
import { RoleBridge } from '@zeki.chat/apps/dist/server/bridges/RoleBridge';
import type { IRole } from '@zeki.chat/core-typings';
import { Roles } from '@zeki.chat/models';

export class AppRoleBridge extends RoleBridge {
	constructor(private readonly orch: IAppServerOrchestrator) {
		super();
	}

	protected async getOneByIdOrName(idOrName: IAppsRole['id'] | IAppsRole['name'], appId: string): Promise<IAppsRole | null> {
		this.orch.debugLog(`The App ${appId} is getting the roleByIdOrName: "${idOrName}"`);

		// #TODO: #AppsEngineTypes - Remove explicit types and typecasts once the apps-engine definition/implementation mismatch is fixed.
		const role: IRole | null = await Roles.findOneByIdOrName(idOrName);
		return this.orch
			.getConverters()
			?.get('roles')
			.convertRole(role as IRole);
	}

	protected async getCustomRoles(appId: string): Promise<Array<IAppsRole>> {
		this.orch.debugLog(`The App ${appId} is getting the custom roles`);

		const cursor = Roles.findCustomRoles();

		const roles: IAppsRole[] = [];

		for await (const role of cursor) {
			const convRole = await this.orch.getConverters()?.get('roles').convertRole(role);
			roles.push(convRole);
		}

		return roles;
	}
}
