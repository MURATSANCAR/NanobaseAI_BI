declare module 'meteor/webapp-hashing' {
	import type { IZekiChatAssetCache } from '@zeki.chat/core-typings';

	namespace WebAppHashing {
		function calculateClientHash(
			manifest: IZekiChatAssetCache[],
			includeFilter?: (type: IZekiChatAssetCache['type'], replaceable: boolean) => boolean,
			runtimeConfigOverride?: unknown,
		): string;
	}
}
