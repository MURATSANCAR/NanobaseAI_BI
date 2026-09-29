import { Callout } from '@rocket.chat/fuselage';
import { useEndpoint } from '@rocket.chat/ui-contexts';
import { useQuery } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';

import EditDepartment from './EditDepartment';
import PageSkeleton from '../../../components/PageSkeleton';

type NewDepartmentProps = {
	id?: string;
};

const NewDepartment = ({ id }: NewDepartmentProps) => {
	const { t } = useTranslation();
	const getDepartmentCreationAvailable = useEndpoint('GET', '/v1/livechat/department/isDepartmentCreationAvailable');
	const { data, isPending, isError } = useQuery({
		queryKey: ['getDepartments'],
		queryFn: () => getDepartmentCreationAvailable(),
	});

	// Zeki: vendor plan modal removed; unavailable creation just renders the skeleton gate below

	if (isError) {
		return <Callout type='danger'>{t('Unavailable')}</Callout>;
	}

	if (!data || isPending || !data.isDepartmentCreationAvailable) {
		return <PageSkeleton />;
	}

	return <EditDepartment id={id} title={t('New_Department')} />;
};

export default NewDepartment;
