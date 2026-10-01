import { ContextualbarIcon, Skeleton, Tabs, TabsItem } from '@rocket.chat/fuselage';
import { useDebouncedValue, useEffectEvent } from '@rocket.chat/fuselage-hooks';
import type { OptionProp } from '@zeki.chat/ui-client';
import {
	ContextualbarHeader,
	ContextualbarTitle,
	ContextualbarClose,
	ContextualbarDialog,
	usePagination,
	useSort,
	Page,
	PageHeader,
	PageContent,
} from '@zeki.chat/ui-client';
import { useRouteParameter, useTranslation, useRouter, useEndpoint } from '@zeki.chat/ui-contexts';
import { useQuery } from '@tanstack/react-query';
import type { ReactElement } from 'react';
import { useEffect, useMemo, useRef, useState } from 'react';

import AdminInviteUsers from './AdminInviteUsers';
import AdminUserCreated from './AdminUserCreated';
import AdminUserForm from './AdminUserForm';
import AdminUserFormWithData from './AdminUserFormWithData';
import AdminUserInfoWithData from './AdminUserInfoWithData';
import UsersPageHeaderContent from './UsersPageHeaderContent';
import UsersTable from './UsersTable';
import useFilteredUsers from './hooks/useFilteredUsers';
import usePendingUsersCount from './hooks/usePendingUsersCount';

export type UsersFilters = {
	text: string;
	roles: OptionProp[];
};

export type AdminUsersTab = 'all' | 'active' | 'deactivated' | 'pending';

export type UsersTableSortingOption = 'name' | 'username' | 'emails.address' | 'status' | 'active' | 'freeSwitchExtension';

const AdminUsersPage = (): ReactElement => {
	const t = useTranslation();

	const router = useRouter();
	const context = useRouteParameter('context');
	const id = useRouteParameter('id');

	const getRoles = useEndpoint('GET', '/v1/roles.list');
	const { data, error } = useQuery({
		queryKey: ['roles'],
		queryFn: async () => getRoles(),
	});

	const paginationData = usePagination();
	const sortData = useSort<UsersTableSortingOption>('name');

	const [tab, setTab] = useState<AdminUsersTab>('all');
	const [userFilters, setUserFilters] = useState<UsersFilters>({ text: '', roles: [] });

	const searchTerm = useDebouncedValue(userFilters.text, 500);
	const prevSearchTerm = useRef('');

	const filteredUsersQueryResult = useFilteredUsers({
		searchTerm,
		prevSearchTerm,
		sortData,
		paginationData,
		tab,
		selectedRoles: useMemo(() => userFilters.roles.map((role) => role.id), [userFilters.roles]),
	});

	const pendingUsersCount = usePendingUsersCount(filteredUsersQueryResult.data?.users);

	const handleReload = (): void => {
		filteredUsersQueryResult?.refetch();
	};

	const handleTabChange = (tab: AdminUsersTab) => {
		setTab(tab);

		paginationData.setCurrent(0);
		sortData.setSort(tab === 'pending' ? 'active' : 'name', 'asc');
	};

	const handleCloseContextualbar = useEffectEvent(() => router.navigate('/admin/users'));

	useEffect(() => {
		prevSearchTerm.current = searchTerm;
	}, [searchTerm]);

	return (
		<Page flexDirection='row'>
			<Page>
				<PageHeader title={t('Users')}>
					<UsersPageHeaderContent />
				</PageHeader>
				<Tabs>
					<TabsItem selected={!tab || tab === 'all'} onClick={() => handleTabChange('all')}>
						{t('All')}
					</TabsItem>
					<TabsItem selected={tab === 'pending'} onClick={() => handleTabChange('pending')} display='flex' flexDirection='row'>
						{`${t('Pending')} `}
						{pendingUsersCount.isLoading && <Skeleton variant='circle' height='x16' width='x16' mis={8} />}
						{pendingUsersCount.isSuccess && `(${pendingUsersCount.data})`}
					</TabsItem>
					<TabsItem selected={tab === 'active'} onClick={() => handleTabChange('active')}>
						{t('Active')}
					</TabsItem>
					<TabsItem selected={tab === 'deactivated'} onClick={() => handleTabChange('deactivated')}>
						{t('Deactivated')}
					</TabsItem>
				</Tabs>
				<PageContent>
					<UsersTable
						users={filteredUsersQueryResult.data?.users || []}
						isLoading={filteredUsersQueryResult.isLoading}
						isError={filteredUsersQueryResult.isError}
						isSuccess={filteredUsersQueryResult.isSuccess}
						total={filteredUsersQueryResult.data?.total || 0}
						setUserFilters={setUserFilters}
						paginationData={paginationData}
						sortData={sortData}
						tab={tab}
						roleData={data}
						onReload={handleReload}
					/>
				</PageContent>
			</Page>
			{context && (
				<ContextualbarDialog onClose={handleCloseContextualbar}>
					<ContextualbarHeader>
						{['new', 'created', 'upgrade'].includes(context) && <ContextualbarIcon name='user-plus' />}
						<ContextualbarTitle>
							{context === 'info' && t('User_Info')}
							{context === 'edit' && t('Edit_User')}
							{(context === 'new' || context === 'created') && t('New_user')}
							{context === 'invite' && t('Invite_Users')}
						</ContextualbarTitle>
						<ContextualbarClose onClick={handleCloseContextualbar} />
					</ContextualbarHeader>
					{context === 'info' && id && <AdminUserInfoWithData uid={id} onReload={handleReload} tab={tab} />}
					{context === 'edit' && id && (
						<AdminUserFormWithData uid={id} onReload={handleReload} context={context} roleData={data} roleError={error} />
					)}
					{context === 'new' && (
						<AdminUserForm onReload={handleReload} context={context} roleData={data} roleError={error} />
					)}
					{context === 'created' && id && <AdminUserCreated uid={id} />}
					{context === 'invite' && <AdminInviteUsers />}
				</ContextualbarDialog>
			)}
		</Page>
	);
};

export default AdminUsersPage;
