import type { IControl } from '@zeki.chat/core-typings';
import type { IMigrationsModel } from '@zeki.chat/model-typings';
import type { Db } from 'mongodb';

import { BaseRaw } from './BaseRaw';

export class MigrationsRaw extends BaseRaw<IControl> implements IMigrationsModel {
	constructor(db: Db) {
		super(db, 'migrations', undefined, {
			collectionNameResolver(name) {
				return name;
			},
		});
	}
}
