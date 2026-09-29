import type { IZekiChatRecord } from './IZekiChatRecord';

export interface ILivechatCustomField extends IZekiChatRecord {
	label: string;
	scope: 'visitor' | 'room';
	visibility: string;
	type?: string;
	regexp?: string;
	required?: boolean;
	defaultValue?: string;
	options?: string;
	public?: boolean;
	searchable?: boolean;
}
