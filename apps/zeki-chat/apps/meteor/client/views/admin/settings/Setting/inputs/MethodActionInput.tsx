import type { ServerMethods } from '@zeki.chat/ddp-client';
import { useMethod } from '@zeki.chat/ui-contexts';

import type { ActionInputBaseProps } from './ActionInputBase';
import ActionInputBase from './ActionInputBase';

type MethodActionInputProps = Omit<ActionInputBaseProps, 'onAction'> & {
	value: keyof ServerMethods;
};

function MethodActionInput({ value, ...rest }: MethodActionInputProps) {
	const actionMethod = useMethod(value);
	return <ActionInputBase onAction={actionMethod} {...rest} />;
}

export default MethodActionInput;
