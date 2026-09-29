import type { IZekiChatRecord } from '../../IZekiChatRecord';

// eslint-disable-next-line @typescript-eslint/naming-convention
export interface FederationKey extends IZekiChatRecord {
	_id: string;
	type: 'private' | 'public';
	key: string;
}
