import type { IAuthorizationLivechat } from '@zeki.chat/core-services';
import { ServiceClassInternal } from '@zeki.chat/core-services';
import type { IUser, IOmnichannelRoom } from '@zeki.chat/core-typings';

import { validators } from './roomAccessValidator.compatibility';

export class AuthorizationLivechat extends ServiceClassInternal implements IAuthorizationLivechat {
	protected name = 'authorization-livechat';

	protected override internal = true;

	async canAccessRoom(room: IOmnichannelRoom, user?: Pick<IUser, '_id'>, extraData?: object): Promise<boolean> {
		for (const validator of validators) {
			if (await validator(room, user, extraData)) {
				return true;
			}
		}

		return false;
	}
}
