import type { ReactNode } from 'react';
import { ErrorBoundary } from 'react-error-boundary';

import AppErrorPage from './AppErrorPage';

type OutermostErrorBoundaryProps = {
	children: ReactNode;
};

// Zeki: crash reporting to an external service was removed; errors stay in the browser.
const OutermostErrorBoundary = ({ children }: OutermostErrorBoundaryProps) => (
	<ErrorBoundary fallbackRender={({ error, resetErrorBoundary }) => <AppErrorPage error={error} clearError={resetErrorBoundary} />}>
		{children}
	</ErrorBoundary>
);

export default OutermostErrorBoundary;
