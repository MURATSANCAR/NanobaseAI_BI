import { TextInput, Field, FieldLabel, FieldRow } from '@rocket.chat/fuselage';
import type { ComponentProps } from 'react';

import { useHasCapability } from '../../../hooks/useHasCapability';

export const EeTextInput = ({ label, ...props }: { label: string } & ComponentProps<typeof TextInput>) => {
	const { data: hasLicense = false } = useHasCapability('livechat-enterprise');

	if (!hasLicense) {
		return null;
	}

	return (
		<Field>
			<FieldLabel>{label}</FieldLabel>
			<FieldRow>
				<TextInput {...props} />
			</FieldRow>
		</Field>
	);
};

export default EeTextInput;
