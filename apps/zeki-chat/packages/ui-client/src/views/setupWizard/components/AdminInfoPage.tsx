import { useTranslation } from 'react-i18next';

import { controlStyle, Field, SetupForm } from './SetupForm';

type AdminData = { fullname: string; username: string; email: string; password: string };
type Props = {
	currentStep: number; stepCount: number; passwordRulesHint: string;
	validateEmail: (value: string) => boolean | string;
	validateUsername: (value: string) => boolean | string;
	validatePassword: (value: string) => boolean | string;
	onSubmit: (data: AdminData) => Promise<void>;
};

const AdminInfoPage = ({ onSubmit, validateEmail, validateUsername, validatePassword, passwordRulesHint, ...steps }: Props) => {
	const { t } = useTranslation('translation');
	const submit = async (form: FormData) => {
		const data: AdminData = { fullname: String(form.get('fullname') || '').trim(), username: String(form.get('username') || '').trim(), email: String(form.get('email') || '').trim(), password: String(form.get('password') || '') };
		for (const result of [validateUsername(data.username), validateEmail(data.email), validatePassword(data.password)]) {
			if (result !== true) throw new Error(typeof result === 'string' ? result : t('Invalid_parameters'));
		}
		await onSubmit(data);
	};
	return <SetupForm title={t('Administrator')} {...steps} onSubmit={submit}>
		<Field label={t('Name')}><input name='fullname' autoComplete='name' required style={controlStyle} /></Field>
		<Field label={t('Username')}><input name='username' autoComplete='username' required style={controlStyle} /></Field>
		<Field label={t('Email')}><input name='email' type='email' autoComplete='email' required style={controlStyle} /></Field>
		<Field label={t('Password')}><input name='password' type='password' autoComplete='new-password' aria-describedby='setup-password-hint' required style={controlStyle} /></Field>
		{passwordRulesHint && <p id='setup-password-hint' style={{ overflowWrap: 'anywhere' }}>{passwordRulesHint}</p>}
	</SetupForm>;
};
export default AdminInfoPage;
