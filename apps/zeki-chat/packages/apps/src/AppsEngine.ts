export type { AppStatus } from '@zeki.chat/apps-engine/definition/AppStatus';
export type {
	IDepartment as IAppsDepartment,
	ILivechatMessage as IAppsLivechatMessage,
	ILivechatRoom as IAppsLivechatRoom,
	IVisitor as IAppsVisitor,
	IVisitorEmail as IAppsVisitorEmail,
	IVisitorPhone as IAppsVisitorPhone,
	ILivechatContact as IAppsLivechatContact,
} from '@zeki.chat/apps-engine/definition/livechat';
export type { IMessage as IAppsMessage } from '@zeki.chat/apps-engine/definition/messages';
export type { IMessageRaw as IAppsMesssageRaw } from '@zeki.chat/apps-engine/definition/messages';
export { AppInterface as AppEvents } from '@zeki.chat/apps-engine/definition/metadata';
export type { IUser as IAppsUser } from '@zeki.chat/apps-engine/definition/users';
export type { IRole as IAppsRole } from '@zeki.chat/apps-engine/definition/roles';
export type { IRoom as IAppsRoom, IRoomRaw as IAppsRoomRaw } from '@zeki.chat/apps-engine/definition/rooms';
export type { ISetting as IAppsSetting } from '@zeki.chat/apps-engine/definition/settings';
export type { IUpload as IAppsUpload } from '@zeki.chat/apps-engine/definition/uploads';
export type {
	IVideoConference as IAppsVideoConference,
	VideoConference as AppsVideoConference,
} from '@zeki.chat/apps-engine/definition/videoConferences';
export { AppManager } from './server/AppManager';
export { AppBridges } from './server/bridges';
export { AppMetadataStorage } from './server/storage';
