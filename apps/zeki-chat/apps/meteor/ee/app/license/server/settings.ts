import { settingsRegistry } from '../../../../app/settings/server';

// Zeki: license key/data/status settings removed — licenses can't be entered or synced.
await settingsRegistry.addGroup('Enterprise', async function () {
	await this.add('Cloud_Workspace_AirGapped_Restrictions_Remaining_Days', -1, {
		type: 'int',
		readonly: true,
		public: true,
	});
});
