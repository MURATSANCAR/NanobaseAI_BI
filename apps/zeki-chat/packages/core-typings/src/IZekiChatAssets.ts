export interface IZekiChatAssetConstraint {
	type: string;
	extensions: string[];
	width?: number;
	height?: number;
}

export interface IZekiChatAssetCache {
	path: string;
	cacheable: boolean;
	where: string;
	type: string;
	content?: Buffer;
	extension?: string;
	url: string;
	size?: number;
	uploadDate?: Date;
	contentType?: string;
	hash: string;
	sourceMapUrl?: string;
}

export interface IZekiChatAsset {
	label: string;
	constraints: IZekiChatAssetConstraint;
	defaultUrl?: string;
	url?: string;
	wizard?: {
		step: number;
		order: number;
	};
	cache?: IZekiChatAssetCache;
}

export interface IZekiChatAssets {
	logo: IZekiChatAsset;
	logo_dark: IZekiChatAsset;
	background: IZekiChatAsset;
	background_dark: IZekiChatAsset;
	favicon_ico: IZekiChatAsset;
	favicon: IZekiChatAsset;
	favicon_16: IZekiChatAsset;
	favicon_32: IZekiChatAsset;
	favicon_192: IZekiChatAsset;
	favicon_512: IZekiChatAsset;
	touchicon_180: IZekiChatAsset;
	touchicon_180_pre: IZekiChatAsset;
	tile_70: IZekiChatAsset;
	tile_144: IZekiChatAsset;
	tile_150: IZekiChatAsset;
	tile_310_square: IZekiChatAsset;
	tile_310_wide: IZekiChatAsset;
	safari_pinned: IZekiChatAsset;
	livechat_widget_logo: IZekiChatAsset;
}
