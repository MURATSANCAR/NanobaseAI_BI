import { faker } from '@faker-js/faker';
import { mockAppRoot } from '@zeki.chat/mock-providers';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import AppStatus from './AppStatus';
import { mockedAppsContext } from '../../../../../../tests/mocks/client/marketplace';
import { createFakeApp, createFakeCapabilities } from '../../../../../../tests/mocks/data';

it('should look good', async () => {
	const app = createFakeApp();

	render(<AppStatus app={app} showStatus isAppDetailsPage />, {
		wrapper: mockAppRoot()
			.withJohnDoe()
			.withEndpoint('GET', '/apps/count', async () => ({
				installedApps: faker.number.int({ min: 0 }),
				totalMarketplaceEnabled: faker.number.int({ min: 0 }),
				totalPrivateEnabled: faker.number.int({ min: 0 }),
			}))
			.withEndpoint('GET', '/v1/capabilities.info', async () => ({
				capabilities: createFakeCapabilities(),
			}))
			.wrap(mockedAppsContext)
			.build(),
	});

	await userEvent.click(screen.getByRole('button', { name: 'Request' }));
});
