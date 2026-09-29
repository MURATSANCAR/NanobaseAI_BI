import type { CapabilityModule } from '@rocket.chat/core-typings';
import { useCapabilitiesBase } from '@rocket.chat/ui-client';

export const useHasCapability = (module: CapabilityModule | undefined) =>
	useCapabilitiesBase({ select: (data) => !!module && data.capabilities.modules.includes(module) });
