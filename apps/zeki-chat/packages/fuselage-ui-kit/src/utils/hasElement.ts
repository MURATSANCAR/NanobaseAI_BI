import type * as UiKit from '@zeki.chat/ui-kit';

type LayoutBlockWithElement = Extract<UiKit.LayoutBlock, { element: UiKit.BlockElement | UiKit.TextObject }>;

export const hasElement = (block: UiKit.LayoutBlock): block is LayoutBlockWithElement => 'element' in block;
