import type * as MessageParser from '@zeki.chat/message-parser';
import type { ReactElement } from 'react';

import InlineElements from '../elements/InlineElements';

type ParagraphBlockProps = {
	children: MessageParser.Inlines[];
};

const ParagraphBlock = ({ children }: ParagraphBlockProps): ReactElement => (
	<div>
		<InlineElements>{children}</InlineElements>
	</div>
);

export default ParagraphBlock;
