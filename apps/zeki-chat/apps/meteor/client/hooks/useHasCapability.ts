import type { CapabilityModule } from '@zeki.chat/core-typings';
import { useCapabilitiesBase } from '@zeki.chat/ui-client';

export const useHasCapability = (module: CapabilityModule | undefined) =>
	useCapabilitiesBase({ select: (data) => !!module && data.capabilities.modules.includes(module) });
