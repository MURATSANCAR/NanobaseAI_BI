import type { IZekiChatRecord } from './IZekiChatRecord';
import type { IUserStatus } from './IUserStatus';

export interface ICustomUserStatus extends IUserStatus, IZekiChatRecord {}
