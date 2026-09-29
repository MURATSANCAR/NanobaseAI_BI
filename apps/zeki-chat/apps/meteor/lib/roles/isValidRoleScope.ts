import type { IRole } from '@zeki.chat/core-typings';

export const isValidRoleScope = (scope: IRole['scope']): boolean => ['Users', 'Subscriptions'].includes(scope);
