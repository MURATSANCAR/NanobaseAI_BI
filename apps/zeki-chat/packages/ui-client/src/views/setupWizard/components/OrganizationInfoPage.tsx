import { useTranslation } from 'react-i18next';

import { controlStyle, Field, SetupForm } from './SetupForm';

type OrganizationData = { organizationName: string; organizationIndustry: string; organizationSize: string; country: string };
type Props = {
	initialValues: OrganizationData; currentStep: number; stepCount: number;
	organizationIndustryOptions: Array<[string, string]>; organizationSizeOptions: Array<[string, string]>; countryOptions: Array<[string, string]>;
	onSubmit: (data: OrganizationData) => Promise<void>; onBackButtonClick?: () => void;
};
const OrganizationInfoPage = ({ initialValues, organizationIndustryOptions, organizationSizeOptions, countryOptions, onSubmit, ...steps }: Props) => {
	const { t } = useTranslation('core');
	const submit = async (form: FormData) => {
		await onSubmit({ organizationName: String(form.get('organizationName') || '').trim(), organizationIndustry: String(form.get('organizationIndustry') || ''), organizationSize: String(form.get('organizationSize') || ''), country: String(form.get('country') || '') });
	};
	const select = (name: keyof OrganizationData, label: string, options: Array<[string, string]>) => <Field label={label}>
		<select name={name} defaultValue={initialValues[name]} required style={controlStyle}>
			<option value=''>{t('Select_an_option')}</option>
			{options.map(([value, text]) => <option key={value} value={value}>{text}</option>)}
		</select>
	</Field>;
	return <SetupForm title={t('onboarding.form.organizationInfoForm.title')} {...steps} onSubmit={submit}>
		<Field label={t('Name')}><input name='organizationName' defaultValue={initialValues.organizationName} autoComplete='organization' required style={controlStyle} /></Field>
		{select('organizationIndustry', t('Industry'), organizationIndustryOptions)}
		{select('organizationSize', t('Size'), organizationSizeOptions)}
		{select('country', t('Country'), countryOptions)}
	</SetupForm>;
};
export default OrganizationInfoPage;
