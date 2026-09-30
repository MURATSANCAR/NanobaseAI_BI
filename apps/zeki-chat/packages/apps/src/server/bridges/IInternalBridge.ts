import type { ISetting } from '@zeki.chat/apps-engine/definition/settings';

export interface IInternalBridge {
	doGetUsernamesOfRoomById(roomId: string): Promise<Array<string>>;
	doGetUsernamesOfRoomByIdSync(roomId: string): Array<string>;
	doGetWorkspacePublicKey(): Promise<ISetting>;
}
