import { addScript } from './inject';
import { settings } from '../../settings/server';

const getContent = (): string => {
	if (process.env.ZEKI_LOCAL_ONLY === 'true') {
		return [
			process.env.DISABLE_ANIMATION ? 'window.DISABLE_ANIMATION = true;' : '',
			settings.get('Accounts_ForgetUserSessionOnWindowClose') ? 'window.Accounts_ForgetUserSessionOnWindowClose = true;' : '',
		].join('\n');
	}

	return `

${process.env.DISABLE_ANIMATION ? 'window.DISABLE_ANIMATION = true;\n' : ''}

// Custom_Script_Logged_Out
window.addEventListener('Custom_Script_Logged_Out', function() {
	${settings.get('Custom_Script_Logged_Out')}
})


// Custom_Script_Logged_In
window.addEventListener('Custom_Script_Logged_In', function() {
	${settings.get('Custom_Script_Logged_In')}
})


// Custom_Script_On_Logout
window.addEventListener('Custom_Script_On_Logout', function() {
	${settings.get('Custom_Script_On_Logout')}
})

${settings.get('Accounts_ForgetUserSessionOnWindowClose') ? `window.Accounts_ForgetUserSessionOnWindowClose = true;` : ''}`;
};

settings.watchMultiple(
	['Custom_Script_Logged_Out', 'Custom_Script_Logged_In', 'Custom_Script_On_Logout', 'Accounts_ForgetUserSessionOnWindowClose'],
	() => {
		const content = getContent();
		addScript('scripts', content);
	},
);
