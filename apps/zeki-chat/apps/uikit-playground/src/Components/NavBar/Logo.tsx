import { Box } from '@rocket.chat/fuselage';
import { ZekiChatLogo } from '@zeki.chat/logo';

const Logo = () => (
	<Box display='flex' justifyContent='center' height='100%' width='var(--sidebar-width)'>
		<Box height='100%' width='80%'>
			<ZekiChatLogo />
		</Box>
	</Box>
);

export default Logo;
