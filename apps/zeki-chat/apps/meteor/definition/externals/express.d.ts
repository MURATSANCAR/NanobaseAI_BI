import 'express';

import type { IUser } from '@zeki.chat/core-typings';

declare module 'express' {
	interface Request {
		userId?: string;
		user?: IUser;
		unauthorized?: boolean;
	}
}
