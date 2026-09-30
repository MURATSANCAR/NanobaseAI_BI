import { NavBarGroup, NavBarSection } from '@rocket.chat/fuselage';
import { useLayout } from '@zeki.chat/ui-contexts';

import NavBarPagesGroup from './NavBarPagesGroup';
import SidebarToggler from '../components/SidebarToggler';

const NavBarPagesSection = () => {
	const { sidebar } = useLayout();

	return (
		<NavBarSection>
			{sidebar.shouldToggle && (
				<>
					<NavBarGroup>
						<SidebarToggler />
					</NavBarGroup>
				</>
			)}
			<NavBarPagesGroup />
		</NavBarSection>
	);
};

export default NavBarPagesSection;
