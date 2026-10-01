import { useLayout } from '@zeki.chat/ui-contexts';

export const useEmbeddedLayout = () => useLayout().isEmbedded;
