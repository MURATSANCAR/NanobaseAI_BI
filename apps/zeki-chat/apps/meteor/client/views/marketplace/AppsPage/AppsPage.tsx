import { Page } from '@zeki.chat/ui-client';
import type { ReactElement } from 'react';

import AppsPageContent from './AppsPageContent';

const AppsPage = (): ReactElement => {
	return (
		<Page background='tint'>
			<AppsPageContent />
		</Page>
	);
};

export default AppsPage;
