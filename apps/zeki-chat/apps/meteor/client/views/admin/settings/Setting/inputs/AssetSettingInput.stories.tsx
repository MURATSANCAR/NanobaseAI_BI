import { Field } from '@chat.example.invalid/fuselage';
import type { Meta, StoryFn } from '@storybook/react';

import AssetSettingInput from './AssetSettingInput';

export default {
	component: AssetSettingInput,
	decorators: [
		(fn) => (
			<div>
				<div>
					<Field>{fn()}</Field>
				</div>
			</div>
		),
	],
} satisfies Meta<typeof AssetSettingInput>;

const Template: StoryFn<typeof AssetSettingInput> = (args) => <AssetSettingInput {...args} />;

export const Default = Template.bind({});
Default.args = {
	_id: 'setting_id',
	label: 'Label',
};

export const WithValue = Template.bind({});
WithValue.args = {
	_id: 'setting_id',
	label: 'Label',
	value: { url: 'https://chat.example.invalid/images/logo.svg' },
};

export const WithFileConstraints = Template.bind({});
WithFileConstraints.args = {
	_id: 'setting_id',
	label: 'Label',
	fileConstraints: { extensions: ['png', 'jpg', 'gif'] },
};
