import { AbacService } from '@zeki.chat/abac';
import { api } from '@zeki.chat/core-services';

import { isRunningMs } from '../../../server/lib/isRunningMs';
import { CapabilitiesService } from '../../app/capabilities/server/capabilities.internalService';
import { OmnichannelEE } from '../../app/livechat-enterprise/server/services/omnichannel.internalService';
import { EnterpriseSettings } from '../../app/settings/server/settings.internalService';
import { InstanceService } from '../local-services/instance/service';
import { LDAPEEService } from '../local-services/ldap/service';
import { MessageReadsService } from '../local-services/message-reads/service';

// Local service implementations are registered independently of subscription state.
api.registerService(new EnterpriseSettings());
api.registerService(new LDAPEEService());
api.registerService(new CapabilitiesService());
api.registerService(new MessageReadsService());
api.registerService(new OmnichannelEE());

// when not running micro services we want to start up the instance intercom
if (!isRunningMs()) {
	api.registerService(new AbacService());
	api.registerService(new InstanceService());
}
