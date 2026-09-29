import '@zeki.chat/ui-contexts';

declare module '@zeki.chat/ui-contexts' {
	interface ServerMethods {
		ufsComplete(fileId: string, storeName: string, token: string): void;
	}
}
