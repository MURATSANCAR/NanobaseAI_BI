import { SidebarV2Banner } from '@rocket.chat/fuselage';

import AirGappedRestrictionWarning from './AirGappedRestrictionWarning';

const AirGappedRestrictionSection = ({ isRestricted, remainingDays }: { isRestricted: boolean; remainingDays: number }) => {
	return (
		<SidebarV2Banner
			title={<AirGappedRestrictionWarning isRestricted={isRestricted} remainingDays={remainingDays} />}
		/>
	);
};

export default AirGappedRestrictionSection;
