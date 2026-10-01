import type { IZekiChatDesktop } from '@zeki.chat/desktop-api';

declare global {
	interface Window {
		ZekiChatDesktop?: IZekiChatDesktop;
	}
}
