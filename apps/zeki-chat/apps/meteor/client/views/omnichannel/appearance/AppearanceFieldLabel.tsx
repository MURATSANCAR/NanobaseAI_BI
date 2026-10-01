import { FieldLabel } from '@rocket.chat/fuselage';
import type { ComponentProps } from 'react';

type AppearanceFieldLabelProps = ComponentProps<typeof FieldLabel> & { premium?: boolean; children: string };
const AppearanceFieldLabel = ({ children, premium: _premium, ...props }: AppearanceFieldLabelProps) => <FieldLabel {...props}>{children}</FieldLabel>;
export default AppearanceFieldLabel;
