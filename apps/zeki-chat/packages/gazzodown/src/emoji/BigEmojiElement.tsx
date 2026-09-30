import type * as MessageParser from '@zeki.chat/message-parser';
import type { ReactElement } from 'react';

import Emoji from './Emoji';

type BigEmojiElementProps = MessageParser.Emoji;

const BigEmojiElement = (emoji: BigEmojiElementProps): ReactElement => <Emoji big {...emoji} />;

export default BigEmojiElement;
