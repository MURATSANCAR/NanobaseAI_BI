import type * as MessageParser from '@zeki.chat/message-parser';
import type { ReactElement } from 'react';

import Emoji from './Emoji';

type PreviewEmojiElementProps = MessageParser.Emoji;

const PreviewEmojiElement = (emoji: PreviewEmojiElementProps): ReactElement => <Emoji preview {...emoji} />;

export default PreviewEmojiElement;
