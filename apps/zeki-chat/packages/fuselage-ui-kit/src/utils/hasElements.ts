import type * as UiKit from '@zeki.chat/ui-kit';

type LayoutBlockWithElements = Extract<UiKit.LayoutBlock, { elements: readonly (UiKit.BlockElement | UiKit.TextObject)[] }>;

export const hasElements = (block: UiKit.LayoutBlock): block is LayoutBlockWithElements =>
	'elements' in block && Array.isArray(block.elements);
