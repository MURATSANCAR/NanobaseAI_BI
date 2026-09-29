import { Permissions } from '@zeki.chat/models';

import { addMigration } from '../../lib/migrations';

addMigration({
	version: 305,
	name: 'Remove unused view-history permission',
	async up() {
		await Permissions.deleteOne({ _id: 'view-history' });
	},
});
