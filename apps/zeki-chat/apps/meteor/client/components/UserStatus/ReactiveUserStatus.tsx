import type { IUser } from '@zeki.chat/core-typings';
import { UserStatus } from '@zeki.chat/ui-client';
import { useUserPresence } from '@zeki.chat/ui-contexts';
import type { ComponentProps, ReactElement } from 'react';
import { memo } from 'react';

type ReactiveUserStatusProps = {
	uid: IUser['_id'];
} & ComponentProps<typeof UserStatus.UserStatus>;

const ReactiveUserStatus = ({ uid, ...props }: ReactiveUserStatusProps): ReactElement => {
	const status = useUserPresence(uid)?.status;
	return <UserStatus.UserStatus status={status} {...props} />;
};

export default memo(ReactiveUserStatus);
