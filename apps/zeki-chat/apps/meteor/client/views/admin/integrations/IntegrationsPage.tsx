import { Button, ButtonGroup, Tabs } from '@rocket.chat/fuselage';
import { Page, PageHeader, PageContent } from '@zeki.chat/ui-client';
import { useRouteParameter, useRouter } from '@zeki.chat/ui-contexts';
import type { ReactElement } from 'react';
import { useTranslation } from 'react-i18next';

import IntegrationsTable from './IntegrationsTable';
import NewBot from './NewBot';

const IntegrationsPage = (): ReactElement => {
	const { t } = useTranslation();
	const router = useRouter();
	const context = useRouteParameter('context');

	const showTable = !['bots'].includes(context || '');

	return (
		<Page flexDirection='column'>
			<PageHeader title={t('Integrations')}>
				<ButtonGroup>
					<Button
						primary
						onClick={() => router.navigate(`/admin/integrations/new/${context === 'webhook-outgoing' ? 'outgoing' : 'incoming'}`)}
					>
						{t('New')}
					</Button>
				</ButtonGroup>
			</PageHeader>
			<Tabs>
				<Tabs.Item selected={!context} onClick={() => router.navigate('/admin/integrations')}>
					{t('All')}
				</Tabs.Item>
				<Tabs.Item selected={context === 'webhook-incoming'} onClick={() => router.navigate('/admin/integrations/webhook-incoming')}>
					{t('Incoming')}
				</Tabs.Item>
				<Tabs.Item selected={context === 'webhook-outgoing'} onClick={() => router.navigate('/admin/integrations/webhook-outgoing')}>
					{t('Outgoing')}
				</Tabs.Item>
				<Tabs.Item selected={context === 'bots'} onClick={() => router.navigate('/admin/integrations/bots')}>
					{t('Bots')}
				</Tabs.Item>
			</Tabs>
			<PageContent>
				{context === 'bots' && <NewBot />}
				{showTable && <IntegrationsTable type={context} />}
			</PageContent>
		</Page>
	);
};

export default IntegrationsPage;
