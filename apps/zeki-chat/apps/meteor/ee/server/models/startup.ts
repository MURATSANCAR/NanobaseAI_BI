import { Capabilities } from '@zeki.chat/capabilities';

// To facilitate our lives with the stream
// Collection will be registered on CE too
// No functionality will be imported tho, just the service registration
import('./OmnichannelServiceLevelAgreements');
import('./AuditLog');
import('./ReadReceipts');
import('./ReadReceiptsArchive');

void Capabilities.whenFeature('livechat-enterprise', () => {
	import('./CannedResponse');
	import('./LivechatTag');
	import('./LivechatUnit');
	import('./LivechatUnitMonitors');
	import('./LivechatRooms');
	import('./LivechatInquiry');
	import('./LivechatDepartment');
	import('./Users');
	import('./LivechatDepartmentAgents');
});
