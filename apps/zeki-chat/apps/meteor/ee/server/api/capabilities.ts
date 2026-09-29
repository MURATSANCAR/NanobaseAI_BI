import { Capabilities } from '@zeki.chat/capabilities';
import { API } from '../../../app/api/server/api';

API.v1.addRoute('capabilities.info', { authRequired: true }, {
	async get() { return API.v1.success({ capabilities: { modules: Capabilities.getModules() } }); },
});
