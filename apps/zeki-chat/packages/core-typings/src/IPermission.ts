import type { IZekiChatRecord } from './IZekiChatRecord';

export interface IPermission extends IZekiChatRecord {
	roles: string[];
	// TODO: migrate settings with group and section with null to undefined
	group?: string | null;
	section?: string | null;
	groupPermissionId?: string;
	level?: 'settings';
	sectionPermissionId?: string;
	settingId?: string;
	sorter?: number;
}
