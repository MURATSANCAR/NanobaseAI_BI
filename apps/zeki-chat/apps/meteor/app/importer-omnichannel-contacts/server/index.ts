import { Capabilities } from '@zeki.chat/capabilities';

import { ContactImporter } from './ContactImporter';
import { Importers } from '../../importer/server';

Capabilities.onFeature('contact-id-verification', () => {
	Importers.add({
		key: 'omnichannel_contact',
		name: 'omnichannel_contacts_importer',
		importer: ContactImporter,
	});
});
