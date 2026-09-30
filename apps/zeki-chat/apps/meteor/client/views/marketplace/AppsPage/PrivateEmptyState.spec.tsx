import { mockAppRoot } from '@zeki.chat/mock-providers';
import { render, screen } from '@testing-library/react';

import PrivateEmptyState from './PrivateEmptyState';

it('shows the private app empty state without a plan upgrade prompt', () => {
	render(<PrivateEmptyState />, {
		wrapper: mockAppRoot().withTranslations('en', 'core', {
			No_private_apps_installed: 'No private apps installed',
		}).build(),
	});
	expect(screen.getByRole('heading', { name: 'No private apps installed' })).toBeInTheDocument();
});
