import { mockAppRoot } from '@zeki.chat/mock-providers';
import { render, screen } from '@testing-library/react';

import '@testing-library/jest-dom';

import UsersPageHeaderContent from './UsersPageHeaderContent';

it('should show "Invite" button if has build-register-user permission', () => {
	render(<UsersPageHeaderContent />, {
		wrapper: mockAppRoot().withJohnDoe().withPermission('bulk-register-user').build(),
	});

	expect(screen.getByRole('button', { name: 'Invite' })).toBeInTheDocument();
});

it('should hide "Invite" button if user doesnt have build-register-user permission', () => {
	render(<UsersPageHeaderContent />, {
		wrapper: mockAppRoot().withJohnDoe().build(),
	});

	expect(screen.queryByRole('button', { name: 'Invite' })).not.toBeInTheDocument();
});

it('should show "New User" button if has create-user permission', () => {
	render(<UsersPageHeaderContent />, {
		wrapper: mockAppRoot().withJohnDoe().withPermission('create-user').build(),
	});

	expect(screen.getByRole('button', { name: 'New_user' })).toBeInTheDocument();
});

it('should hide "New User" button if user doesnt have create-user permission', () => {
	render(<UsersPageHeaderContent />, {
		wrapper: mockAppRoot().withJohnDoe().build(),
	});

	expect(screen.queryByRole('button', { name: 'New_user' })).not.toBeInTheDocument();
});
