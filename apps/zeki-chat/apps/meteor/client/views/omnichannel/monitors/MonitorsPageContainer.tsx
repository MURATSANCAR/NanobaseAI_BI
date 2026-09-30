import MonitorsPage from './MonitorsPage';
import PageSkeleton from '../../../components/PageSkeleton';
import { useHasCapability } from '../../../hooks/useHasCapability';
import NotAuthorizedPage from '../../notAuthorized/NotAuthorizedPage';

const MonitorsPageContainer = () => {
	const { isPending, data: hasLicense = false } = useHasCapability('livechat-enterprise');

	if (isPending) {
		return <PageSkeleton />;
	}

	if (!hasLicense) {
		return <NotAuthorizedPage />;
	}

	return <MonitorsPage />;
};

export default MonitorsPageContainer;
